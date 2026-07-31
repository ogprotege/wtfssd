// Scanner.swift — runs ssdwtf scans and parses payloads. Read-only.
//
// Two tiers: fast scans (every refresh tick, ~2 s) feed the title and
// vitals; full scans (every 15 min, and on first detail open) feed the
// detail views (state dirs, ghosts, repos, retention, …).

import Foundation

struct Finding {
    let severity: String
    let code: String
    let title: String
    let detail: String
    let recommendation: String
}

struct Vitals {
    var swapGB: Double?
    var swapTotalGB: Double?
    var diskFreePct: Double?
    var diskSizeGB: Double?
    var diskAvailGB: Double?
    var writeMBs: Double?
    var pressureLevel: Int?
    var smartPercentUsed: Int?
    var smartTBWritten: Double?
    var smartHealth: String?
    var smartModel: String?
    var backupAgeHours: Double?
    var backupConfigured: Bool?
    var backupDestinationPresent: Bool?
    var stateTotalGB: Double?
    var ideProcCount: Int?
    var ghostCount: Int?
}

struct StateDirEntry {
    let key: String
    let sizeBytes: Int64
    let category: String
    let note: String
}

struct GhostEntry {
    let pid: Int
    let name: String
    let ageSeconds: Int
    let rssMB: Double
}

struct RepoEntry {
    let path: String
    let uncommitted: Int
    let untracked: Int
    let unpushed: Int
    let hasRemote: Bool
}

struct RetentionItem {
    let tool: String
    let status: String
    let value: Int?
}

struct Payload {
    let isFull: Bool
    let score: Int
    let grade: String
    let domains: [(name: String, status: String)]
    let findings: [Finding]
    let vitals: Vitals
    let stateDirs: [StateDirEntry]
    let ghosts: [GhostEntry]
    let repos: [RepoEntry]
    let retention: [RetentionItem]
    let crashesWeekly: Int?
    let cpuSpeedLimit: Int?
    let uptimeDays: Double?
    let batteryCycles: Int?
    let batteryMaxPct: Int?
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

    func scan(fast: Bool) throws -> Payload {
        var args = ["scan", "--json", "--no-history"]
        if fast { args.insert("--fast", at: 1) }
        let (exe, finalArgs, cwd): (String, [String], String?) = {
            if let which = try? run("/usr/bin/which", ["ssdwtf"], cwd: nil,
                                    timeout: 10),
               which.status == 0,
               !which.stdout.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return (which.stdout.trimmingCharacters(in: .whitespacesAndNewlines),
                        args, nil)
            }
            return ("/usr/bin/env", ["python3", "-m", "ssdwtf"] + args, repoRoot)
        }()
        let result = try run(exe, finalArgs, cwd: cwd, timeout: fast ? 60 : 120)
        guard let data = result.stdout.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let score = root["score"] as? Int,
              let grade = root["grade"] as? String else {
            throw ScanError.failed
        }
        let report = root["report"] as? [String: Any] ?? [:]
        let rawDomains = root["domains"] as? [String: String] ?? [:]
        let domains = Scanner.domainOrder.map {
            (name: $0, status: rawDomains[$0] ?? "unknown")
        }
        let findings = (root["findings"] as? [[String: Any]] ?? []).compactMap { f -> Finding? in
            guard let sev = f["severity"] as? String,
                  let title = f["title"] as? String else { return nil }
            return Finding(severity: sev,
                           code: f["code"] as? String ?? "",
                           title: title,
                           detail: f["detail"] as? String ?? "",
                           recommendation: f["recommendation"] as? String ?? "")
        }

        var v = Vitals()
        if let swap = report["swap"] as? [String: Any] {
            if let used = swap["used_mb"] as? Double { v.swapGB = used / 1024 }
            if let total = swap["total_mb"] as? Double { v.swapTotalGB = total / 1024 }
        }
        if let disk = report["disk"] as? [String: Any] {
            v.diskFreePct = disk["pct_free"] as? Double
            v.diskSizeGB = disk["size_gb"] as? Double
            v.diskAvailGB = disk["avail_gb"] as? Double
        }
        if let wr = report["writerate"] as? [String: Any] {
            v.writeMBs = wr["mb_per_s"] as? Double
        }
        if let pr = report["pressure"] as? [String: Any] {
            v.pressureLevel = pr["level"] as? Int
        }
        if let smart = report["smart"] as? [String: Any] {
            v.smartPercentUsed = smart["percent_used"] as? Int
            v.smartTBWritten = smart["tb_written"] as? Double
            v.smartHealth = smart["health"] as? String
            v.smartModel = smart["model"] as? String
        }
        if let bu = report["backup"] as? [String: Any] {
            v.backupAgeHours = bu["last_backup_age_hours"] as? Double
            v.backupConfigured = bu["configured"] as? Bool
            v.backupDestinationPresent = bu["destination_present"] as? Bool
        }
        if let sd = report["statedirs"] as? [String: Any],
           let total = sd["total_bytes"] as? Double, total > 0 {
            v.stateTotalGB = total / 1e9
        }
        if let procs = report["processes"] as? [String: Any] {
            v.ideProcCount = procs["total_ide_processes"] as? Int
            v.ghostCount = (procs["ghosts"] as? [[String: Any]])?.count
        }

        let stateDirs = ((report["statedirs"] as? [String: Any])?["dirs"]
                         as? [[String: Any]] ?? []).compactMap { d -> StateDirEntry? in
            guard let key = d["key"] as? String,
                  let exists = d["exists"] as? Bool, exists else { return nil }
            return StateDirEntry(key: key,
                                 sizeBytes: Int64(d["size_bytes"] as? Double ?? 0),
                                 category: d["category"] as? String ?? "",
                                 note: d["note"] as? String ?? "")
        }.sorted { $0.sizeBytes > $1.sizeBytes }

        let ghosts = ((report["processes"] as? [String: Any])?["ghosts"]
                      as? [[String: Any]] ?? []).compactMap { g -> GhostEntry? in
            guard let pid = g["pid"] as? Int,
                  let name = g["name"] as? String else { return nil }
            return GhostEntry(pid: pid, name: name,
                              ageSeconds: g["age_seconds"] as? Int ?? 0,
                              rssMB: g["rss_mb"] as? Double ?? 0)
        }

        let repos = ((report["gitwatch"] as? [String: Any])?["repos"]
                     as? [[String: Any]] ?? []).compactMap { r -> RepoEntry? in
            guard let path = r["path"] as? String else { return nil }
            return RepoEntry(path: path,
                             uncommitted: r["uncommitted"] as? Int ?? 0,
                             untracked: r["untracked"] as? Int ?? 0,
                             unpushed: r["unpushed"] as? Int ?? 0,
                             hasRemote: r["has_remote"] as? Bool ?? true)
        }

        let retention = ((report["retention"] as? [String: Any])?["tools"]
                         as? [[String: Any]] ?? []).compactMap { t -> RetentionItem? in
            guard let tool = t["tool"] as? String else { return nil }
            return RetentionItem(tool: tool,
                                 status: t["status"] as? String ?? "absent",
                                 value: t["value"] as? Int)
        }

        let crashes = (report["crashes"] as? [String: Any])?["total_weekly"] as? Int
        let system = report["system"] as? [String: Any]
        let scannedAt = report["timestamp"] as? String ?? ""

        return Payload(isFull: !fast, score: score, grade: grade,
                       domains: domains, findings: findings, vitals: v,
                       stateDirs: stateDirs, ghosts: ghosts, repos: repos,
                       retention: retention,
                       crashesWeekly: crashes,
                       cpuSpeedLimit: system?["cpu_speed_limit"] as? Int,
                       uptimeDays: system?["uptime_days"] as? Double,
                       batteryCycles: system?["battery_cycle_count"] as? Int,
                       batteryMaxPct: system?["battery_max_capacity_pct"] as? Int,
                       scannedAt: scannedAt)
    }

    struct ProcResult { let stdout: String; let status: Int32 }

    @discardableResult
    private func run(_ exe: String, _ args: [String], cwd: String?,
                     timeout: TimeInterval) throws -> ProcResult {
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
