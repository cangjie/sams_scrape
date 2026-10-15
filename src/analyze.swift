import AppKit
import CoreML
import Foundation
import Vision

// analyze <png> [放大倍数=3]     分析一张图，输出一个 JSON
// analyze --serve [放大倍数=3]   常驻：从标准输入逐行读图片路径，每张图输出一行 JSON（出错输出 {"error":...}）
//
// 常驻模式是给抓取脚本用的：每页新开进程的话，系统有时每次都要重新准备识别模型，一页要等二三十秒；
// 常驻后模型只加载一次。
//
// 输出：
//   width/height  图片像素
//   barY          左侧栏选中项蓝色竖条的中心 y（找不到为 null）
//   listHash      商品列表区域的像素指纹
//   lines[]       每行文字：位置、置信度、前景色 fg、背景色 bg
// 坐标都是原图像素，原点左上。

struct Line: Codable {
    let x: Int, y: Int, w: Int, h: Int
    let conf: Float
    let text: String
    let fg: [Int], bg: [Int]
}
struct Out: Codable {
    let width: Int, height: Int
    let barY: Int?
    let listHash: String
    let lines: [Line]
}
struct Failure: Error { let message: String }

let space = CGColorSpaceCreateDeviceRGB()
let info = CGImageAlphaInfo.premultipliedLast.rawValue

// 识别模型的版本。默认用第 2 版：第 3 版（系统默认）每次加载模型要 20 多秒，而这台机器磁盘紧张，
// 系统会反复清掉它的模型缓存；第 2 版加载只要 2 秒左右，识别结果基本一样。环境变量 SAMS_OCR_REV=3 可切回。
// 用数字而不是 VNRecognizeTextRequestRevision2/3 常量：老的 SDK（10.15）里没有这两个常量，运行时的系统是认的
let ocrRevision: Int = ProcessInfo.processInfo.environment["SAMS_OCR_REV"] == "3" ? 3 : 2

func makeRequest() -> VNRecognizeTextRequest {
    let req = VNRecognizeTextRequest()
    req.revision = ocrRevision
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = false
    // 只用 CPU：神经引擎的编译服务忙的时候，识别要排队等很久
    #if compiler(>=5.9)
    if #available(macOS 14.0, *) {
        if let stages = try? req.supportedComputeStageDevices {
            for (stage, devices) in stages {
                if let cpu = devices.first(where: { if case .cpu = $0 { return true } else { return false } }) {
                    req.setComputeDevice(cpu, for: stage)
                }
            }
        }
    } else {
        req.usesCPUOnly = true
    }
    #else
    req.usesCPUOnly = true                // 老编译器（macOS 14 以前的 SDK）没有按阶段选设备的接口
    #endif
    return req
}

func analyze(_ path: String, _ up: Int) throws -> Data {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        throw Failure(message: "cannot read image")
    }
    let W = cg.width, H = cg.height
    let s = Double(W) / 383.0   // 布局常量按 383 宽的窗口定义

    // 原图像素（RGBA，行序自上而下）
    var buf = [UInt8](repeating: 0, count: W * H * 4)
    guard let ctx = CGContext(data: &buf, width: W, height: H, bitsPerComponent: 8, bytesPerRow: W * 4,
                              space: space, bitmapInfo: info) else { throw Failure(message: "no bitmap context") }
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: W, height: H))

    func px(_ x: Int, _ y: Int) -> (Int, Int, Int) {
        let i = (y * W + x) * 4
        return (Int(buf[i]), Int(buf[i + 1]), Int(buf[i + 2]))
    }

    // 放大后再识别：镜像截图里的小字，放大能明显减少错字
    var ocrImage = cg
    if up > 1, let big = CGContext(data: nil, width: W * up, height: H * up, bitsPerComponent: 8, bytesPerRow: 0,
                                   space: space, bitmapInfo: info) {
        big.interpolationQuality = .high
        big.draw(cg, in: CGRect(x: 0, y: 0, width: W * up, height: H * up))
        if let m = big.makeImage() { ocrImage = m }
    }
    let req = makeRequest()
    try VNImageRequestHandler(cgImage: ocrImage, options: [:]).perform([req])

    // 一个文字框的背景色（出现最多的颜色）和前景色（与背景差别最大的那批像素的平均）
    func colors(_ x0: Int, _ y0: Int, _ w: Int, _ h: Int) -> ([Int], [Int]) {
        let xa = max(0, x0), ya = max(0, y0), xb = min(W, x0 + w), yb = min(H, y0 + h)
        if xb <= xa || yb <= ya { return ([0, 0, 0], [255, 255, 255]) }
        var hist = [Int: (Int, Int, Int, Int)]()
        for y in ya..<yb { for x in xa..<xb {
            let (r, g, b) = px(x, y)
            let k = (r >> 4) << 8 | (g >> 4) << 4 | (b >> 4)
            let v = hist[k] ?? (0, 0, 0, 0)
            hist[k] = (v.0 + 1, v.1 + r, v.2 + g, v.3 + b)
        } }
        guard let top = hist.values.max(by: { $0.0 < $1.0 }) else { return ([0, 0, 0], [255, 255, 255]) }
        let bg = [top.1 / top.0, top.2 / top.0, top.3 / top.0]
        var far: [(Int, Int, Int, Int)] = []
        for y in ya..<yb { for x in xa..<xb {
            let (r, g, b) = px(x, y)
            let d = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
            if d > 60 { far.append((d, r, g, b)) }
        } }
        if far.isEmpty { return (bg, bg) }
        far.sort { $0.0 > $1.0 }
        let n = max(1, far.count / 4)   // 抗锯齿边缘会把颜色冲淡，只取最“实”的那四分之一
        var sr = 0, sg = 0, sb = 0
        for i in 0..<n { sr += far[i].1; sg += far[i].2; sb += far[i].3 }
        return ([sr / n, sg / n, sb / n], bg)
    }

    var lines: [Line] = []
    for o in (req.results as? [VNRecognizedTextObservation]) ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        let x = Int(Double(b.minX) * Double(W)), y = Int((1 - Double(b.maxY)) * Double(H))
        let w = Int(Double(b.width) * Double(W)), h = Int(Double(b.height) * Double(H))
        let (fg, bg) = colors(x, y, w, h)
        lines.append(Line(x: x, y: y, w: w, h: h, conf: c.confidence, text: c.string, fg: fg, bg: bg))
    }
    lines.sort { $0.y == $1.y ? $0.x < $1.x : $0.y < $1.y }

    // 左侧栏选中项的蓝色竖条
    var barRows: [Int] = []
    for y in Int(200 * s)..<min(H, Int(750 * s)) {
        var n = 0
        for x in Int(3 * s)..<Int(15 * s) {
            let (r, g, b) = px(x, y)
            if b > 140 && r < 100 && b - r > 70 && b - g > 20 { n += 1 }
        }
        if n >= 2 { barRows.append(y) }
    }
    let barY: Int? = barRows.count >= Int(10 * s) ? barRows[barRows.count / 2] : nil

    // 商品列表区域指纹（避开右侧会伸缩的悬浮按钮）
    var hash: UInt64 = 1469598103934665603
    var y = Int(255 * s)
    while y < min(H, Int(740 * s)) {
        var x = Int(100 * s)
        while x < min(W, Int(318 * s)) {
            let (r, g, b) = px(x, y)
            for v in [r, g, b] { hash = (hash ^ UInt64(v)) &* 1099511628211 }
            x += 2
        }
        y += 2
    }
    return try JSONEncoder().encode(Out(width: W, height: H, barY: barY, listHash: String(hash, radix: 16), lines: lines))
}

let args = CommandLine.arguments
let out = FileHandle.standardOutput
let nl = "\n".data(using: .utf8)!

if args.count >= 2, args[1] == "--serve" {
    let up = max(1, Int(args.count > 2 ? args[2] : "3") ?? 3)
    while let line = readLine() {
        let path = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if path.isEmpty { continue }
        do {
            out.write(try autoreleasepool { try analyze(path, up) })
        } catch {
            FileHandle.standardError.write("ERR \(error)\n".data(using: .utf8)!); out.write("{\"error\":\"analyze failed\"}".data(using: .utf8)!)
        }
        out.write(nl)
    }
} else if args.count >= 2 {
    let up = max(1, Int(args.count > 2 ? args[2] : "3") ?? 3)
    do {
        out.write(try analyze(args[1], up))
    } catch {
        FileHandle.standardError.write("analyze failed\n".data(using: .utf8)!)
        exit(2)
    }
} else {
    FileHandle.standardError.write("usage: analyze <png> [scale] | analyze --serve [scale]\n".data(using: .utf8)!)
    exit(1)
}
