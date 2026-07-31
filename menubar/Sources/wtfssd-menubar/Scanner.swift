// Scanner.swift — runs `ssdwtf scan --fast --json --no-history` and parses
// the payload. Read-only; owns nothing.

import Foundation

struct Finding {
    let severity: String
    let title: String
}

struct Vitals {
    var swapGB: Double?
    var diskFreePct: Double?
    var writeMBs: Double?
    var pressureLevel: Int?
}

struct Payload {
    let score: Int
    let grade: String
    let domains: [(name: String, status: String)]
    let findings: [Finding]
    let vitals: Vitals
    let scannedAt: String
}

enum ScanError: Error { case failed }

final class Scanner {
    static let domainOrder = ["drive", "backup", "headroom", "memory",
                              "processes", "state", "stability", "telemetry",
                              "privacy", "work"]

    let repoRoot: String

    init() {
        repoRoot = Bundle.main.infoDictionary?["SSDWTFRepoRoot"] as? String
            ?? ("\(NSHomeDirectory())/wtfssd")
    }

    /// One fast scan. Throws on any failure (caller renders the error state).
    func scan() throws -> Payload {
        let (exe, args, cwd): (String, [String], String?) = {
            if let which = try? run("/usr/bin/which", ["ssdwtf"], cwd: nil),
               which.status == 0,
               !which.stdout.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return (which.stdout.trimmingCharacters(in: .whitespacesAndNewlines),
                        ["scan", "--fast", "--json", "--no-history"], nil)
            }
            return ("/usr/bin/env",
                    ["python3", "-m", "ssdwtf", "scan", "--fast", "--json",
                     "--no-history"], repoRoot)
        }()
        let result = try run(exe, args, cwd: cwd, timeout: 60)
        guard let data = result.stdout.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let score = root["score"] as? Int,
              let grade = root["grade"] as? String else {
            throw ScanError.failed
        }
        let rawDomains = root["domains"] as? [String: String] ?? [:]
        let domains = Scanner.domainOrder.map {
            (name: $0, status: rawDomains[$0] ?? "unknown")
        }
        let findings = (root["findings"] as? [[String: Any]] ?? []).compactMap { f -> Finding? in
            guard let sev = f["severity"] as? String,
                  let title = f["title"] as? String else { return nil }
            return Finding(severity: sev, title: title)
        }
        let report = root["report"] as? [String: Any] ?? [:]
        var vitals = Vitals()
        if let swap = report["swap"] as? [String: Any],
           let used = swap["used_mb"] as? Double {
            vitals.swapGB = used / 1024
        }
        if let disk = report["disk"] as? [String: Any],
           let pct = disk["pct_free"] as? Double {
            vitals.diskFreePct = pct
        }
        if let wr = report["writerate"] as? [String: Any],
           let rate = wr["mb_per_s"] as? Double {
            vitals.writeMBs = rate
        }
        if let pr = report["pressure"] as? [String: Any],
           let lvl = pr["level"] as? Int {
            vitals.pressureLevel = lvl
        }
        let scannedAt = report["timestamp"] as? String ?? ""
        return Payload(score: score, grade: grade, domains: domains,
                       findings: findings, vitals: vitals, scannedAt: scannedAt)
    }

    struct ProcResult { let stdout: String; let status: Int32 }

    @discardableResult
    private func run(_ exe: String, _ args: [String], cwd: String?,
                     timeout: TimeInterval = 10) throws -> ProcResult {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        if let cwd { p.currentDirectoryURL = URL(fileURLWithPath: cwd) }
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        try p.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return ProcResult(stdout: String(decoding: data, as: UTF8.self),
                          status: p.terminationStatus)
    }
}
