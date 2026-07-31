// main.swift — native menu bar monitor for ssdwtf (SwiftUI popover).
//
// Owns nothing, deletes nothing: every action is a read-only scan or opens
// Terminal for the user. Debug: `wtfssd-menubar --dump-menu` prints the
// payload summary as text and exits.

import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private let model = MonitorModel()
    private let scanner = Scanner()
    private var timer: Timer?
    private let refreshInterval: TimeInterval = 60

    func applicationDidFinishLaunching(_ notification: Notification) {
        if CommandLine.arguments.contains("--dump-menu") {
            dumpMenu()
            NSApplication.shared.terminate(nil)
            return
        }
        statusItem = NSStatusBar.system.statusItem(
            withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.action = #selector(togglePopover)
            button.target = self
        }
        popover = NSPopover()
        popover.behavior = .transient
        popover.animates = false
        popover.contentViewController = NSHostingController(
            rootView: PopoverView(
                model: model,
                onRefresh: { [weak self] in self?.refresh() },
                onAction: { [weak self] cmd in self?.openInTerminal(cmd) },
                onQuit: { NSApplication.shared.terminate(nil) }))
        renderTitle()
        refresh()
        if CommandLine.arguments.contains("--open") {
            // verification hook: open the popover shortly after launch
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                self.togglePopover()
            }
        }
        timer = Timer.scheduledTimer(withTimeInterval: refreshInterval,
                                     repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    @objc private func togglePopover() {
        guard let button = statusItem.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            refresh()
            fitPopover()
            popover.show(relativeTo: button.bounds, of: button,
                         preferredEdge: .minY)
        }
    }

    /// NSPopover does not auto-fit an NSHostingController: size it from the
    /// SwiftUI view's fitting size, on show and whenever content changes.
    private func fitPopover() {
        guard let vc = popover.contentViewController else { return }
        vc.view.layoutSubtreeIfNeeded()
        let fit = vc.view.fittingSize
        popover.contentSize = NSSize(width: max(292, fit.width),
                                     height: max(120, fit.height))
    }

    @objc func refresh() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            do {
                let payload = try self.scanner.scan()
                DispatchQueue.main.async {
                    self.model.payload = payload
                    self.model.lastError = false
                    self.renderTitle()
                    if self.popover?.isShown == true { self.fitPopover() }
                }
            } catch {
                DispatchQueue.main.async {
                    self.model.lastError = true
                    self.renderTitle()
                }
            }
        }
    }

    private func renderTitle() {
        guard let button = statusItem.button else { return }
        let title = NSMutableAttributedString()
        if let payload = model.payload {
            let worst = payload.findings.reduce("ok") { w, f in
                Theme.severityRank[f.severity, default: 0]
                    > Theme.severityRank[w, default: 0] ? f.severity : w
            }
            title.append(NSAttributedString(string: "SSD ", attributes: [
                .foregroundColor: NSColor.secondaryLabelColor,
                .font: NSFont.systemFont(ofSize: 12, weight: .medium)]))
            title.append(NSAttributedString(
                string: "\(payload.score)·\(payload.grade)", attributes: [
                    .foregroundColor: NSColor(Theme.statusColor(worst)),
                    .font: NSFont.systemFont(ofSize: 12, weight: .bold)]))
        } else {
            title.append(NSAttributedString(string: "SSD ?", attributes: [
                .foregroundColor: NSColor.secondaryLabelColor,
                .font: NSFont.systemFont(ofSize: 12, weight: .medium)]))
        }
        button.attributedTitle = title
    }

    private func openInTerminal(_ subcommand: String) {
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("ssdwtf-\(subcommand).command")
        let script = """
            #!/bin/sh
            cd "\(scanner.repoRoot)" 2>/dev/null
            if command -v ssdwtf >/dev/null 2>&1; then
                ssdwtf \(subcommand)
            else
                python3 -m ssdwtf \(subcommand)
            fi
            echo; echo "— press return to close —"; read -r _
            """
        try? script.write(to: tmp, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes(
            [.posixPermissions: 0o755], ofItemAtPath: tmp.path)
        NSWorkspace.shared.open(tmp)
    }

    private func dumpMenu() {
        if let payload = try? scanner.scan() {
            var lines = ["Health \(payload.score)/100 (\(payload.grade))"]
            for d in payload.domains {
                lines.append("● \(d.name) — \(d.status)")
            }
            print(lines.joined(separator: "\n"))
        } else {
            print("scan failed — is ssdwtf installed?")
        }
    }
}

// MARK: - Entry point

let app = NSApplication.shared

// --snapshot <path>: render the popover view offscreen to a PNG and exit.
if let idx = CommandLine.arguments.firstIndex(of: "--snapshot"),
   idx + 1 < CommandLine.arguments.count {
    let path = CommandLine.arguments[idx + 1]
    let model = MonitorModel()
    model.payload = try? Scanner().scan()
    model.lastError = model.payload == nil
    let view = PopoverView(model: model, onRefresh: {},
                           onAction: { _ in }, onQuit: {})
    let host = NSHostingView(rootView: view)
    host.frame = CGRect(x: 0, y: 0, width: 292, height: 10)
    host.layoutSubtreeIfNeeded()
    let size = host.fittingSize
    host.frame = CGRect(origin: .zero, size: size)
    if let rep = host.bitmapImageRepForCachingDisplay(in: host.bounds) {
        host.cacheDisplay(in: host.bounds, to: rep)
        if let png = rep.representation(using: .png, properties: [:]) {
            try? png.write(to: URL(fileURLWithPath: path))
        }
    }
    exit(0)
}

app.setActivationPolicy(.accessory)  // menu bar only, no Dock icon
let delegate = AppDelegate()
app.delegate = delegate
app.run()
