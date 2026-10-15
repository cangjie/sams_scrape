import AppKit
import CoreGraphics
import Foundation

// 对 iPhone 镜像窗口发鼠标事件。坐标是屏幕坐标（点）。
//   act window                          输出镜像窗口：id x y w h
//   act cursor                          输出当前光标位置
//   act scroll <x> <y> <dy> [steps]     在 (x,y) 处滚动 dy 像素（负数 = 列表往下翻）
//   act click  <x> <y>                  在 (x,y) 处单击
// scroll / click 之前会确认镜像窗口在最前，不在就激活并等 1.5 秒。

let APP = "iPhone Mirroring"
let a = CommandLine.arguments
let src = CGEventSource(stateID: .hidSystemState)

func cursor() -> CGPoint { CGEvent(source: nil)?.location ?? .zero }

func mirrorWindow() -> (Int, Int, Int, Int, Int)? {
    let opts: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
    guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else { return nil }
    for w in list {
        guard (w[kCGWindowOwnerName as String] as? String) == APP,
              (w[kCGWindowLayer as String] as? Int) == 0,
              let b = w[kCGWindowBounds as String] as? [String: Any] else { continue }
        let wd = Int(b["Width"] as? Double ?? 0), ht = Int(b["Height"] as? Double ?? 0)
        if wd < 200 || ht < 400 { continue }
        return (w[kCGWindowNumber as String] as? Int ?? 0, Int(b["X"] as? Double ?? 0), Int(b["Y"] as? Double ?? 0), wd, ht)
    }
    return nil
}

func ensureFront() {
    if NSWorkspace.shared.frontmostApplication?.localizedName == APP { return }
    if let app = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == APP }) {
        app.activate(options: [.activateAllWindows])
        usleep(1_500_000)
        print("activated")
    }
}

func move(_ p: CGPoint) {
    // 只发 mouseMoved 事件光标不会动，必须先 warp
    CGWarpMouseCursorPosition(p)
    CGAssociateMouseAndMouseCursorPosition(1)
    usleep(100_000)
    CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?
        .post(tap: .cghidEventTap)
    usleep(250_000)
}

guard a.count >= 2 else { print("usage: act window|cursor|scroll|click ..."); exit(1) }

switch a[1] {
case "window":
    guard let w = mirrorWindow() else { print("none"); exit(3) }
    let front = NSWorkspace.shared.frontmostApplication?.localizedName == APP ? 1 : 0
    print("\(w.0) \(w.1) \(w.2) \(w.3) \(w.4) \(front)")
case "cursor":
    let c = cursor()
    let keyIdle = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .keyDown)
    print("\(Int(c.x)) \(Int(c.y)) \(String(format: "%.1f", keyIdle))")
case "scroll", "click":
    guard a.count >= 4, let x = Double(a[2]), let y = Double(a[3]) else { print("bad args"); exit(1) }
    let p = CGPoint(x: x, y: y)
    ensureFront()
    move(p)
    if a[1] == "scroll" {
        let dy = Int32(a.count > 4 ? a[4] : "-300") ?? -300
        let steps = max(1, Int32(a.count > 5 ? a[5] : "14") ?? 14)
        for _ in 0..<steps {
            CGEvent(scrollWheelEvent2Source: src, units: .pixel, wheelCount: 1,
                    wheel1: dy / steps, wheel2: 0, wheel3: 0)?.post(tap: .cghidEventTap)
            usleep(20_000)
        }
    } else {
        // 镜像窗口要先“看到”光标在动、停稳，再按下才认；否则点击常被吞掉
        move(CGPoint(x: x - 7, y: y - 5))
        move(p)
        usleep(150_000)
        CGEvent(mouseEventSource: src, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left)?
            .post(tap: .cghidEventTap)
        usleep(80_000)
        CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left)?
            .post(tap: .cghidEventTap)
    }
    let c = cursor()
    print("done \(Int(c.x)) \(Int(c.y))")
default:
    print("unknown command")
    exit(1)
}
