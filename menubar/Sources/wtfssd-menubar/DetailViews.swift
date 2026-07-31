// DetailViews.swift — per-domain detail pages and the settings view.

import SwiftUI
import ServiceManagement

struct DomainDetailView: View {
    let domain: String
    @ObservedObject var model: MonitorModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button { model.selectedDomain = nil } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 11, weight: .bold))
                }
                .buttonStyle(.plain).foregroundStyle(.secondary)
                Text(domain.uppercased()).font(Theme.sectionFont)
                    .foregroundStyle(.secondary)
                Spacer()
                if let p = model.detailPayload,
                   let status = p.domains.first(where: { $0.name == domain })?.status {
                    Text(status).font(Theme.valueFont)
                        .foregroundStyle(Theme.statusColor(status))
                }
            }
            .padding(.bottom, 8)

            if let p = model.detailPayload {
                content(p)
                findingsBlock
            } else {
                Text("no data yet — first full scan pending")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                    .padding(.vertical, 20)
            }
        }
    }

    @ViewBuilder
    private func content(_ p: Payload) -> some View {
        switch domain {
        case "drive":
            kv("model", p.vitals.smartModel ?? "—")
            kv("health", p.vitals.smartHealth ?? "—")
            if let pct = p.vitals.smartPercentUsed {
                MeterRow(name: "wear used", value: "\(pct)%",
                         reference: "of rated life",
                         fraction: Double(pct) / 100, marker: nil,
                         tint: pct >= 90 ? .red : .green)
            }
            kv("lifetime writes", p.vitals.smartTBWritten.map {
                String(format: "%.1f TB", $0) } ?? "—")
        case "backup":
            kv("configured", p.vitals.backupConfigured == true ? "yes" : "no")
            kv("destination", p.vitals.backupDestinationPresent == true
               ? "mounted" : "not mounted")
            MeterRow(name: "last backup",
                     value: p.vitals.backupAgeHours.map {
                        $0 < 48 ? String(format: "%.0f h ago", $0)
                                : String(format: "%.0f d ago", $0 / 24) } ?? "never",
                     reference: "warn 48h · crit 7d",
                     fraction: (p.vitals.backupAgeHours ?? 720) / 168,
                     marker: 48.0 / 168.0,
                     tint: (p.vitals.backupAgeHours ?? 720) >= 168 ? .red
                           : ((p.vitals.backupAgeHours ?? 720) >= 48 ? .orange : .green))
        case "headroom":
            MeterRow(name: "free",
                     value: pct(p.vitals.diskFreePct),
                     reference: "of \(fmt(p.vitals.diskSizeGB, "%.0f GB"))",
                     fraction: (p.vitals.diskFreePct ?? 100) / 100,
                     marker: 0.15,
                     tint: (p.vitals.diskFreePct ?? 100) < 15 ? .orange : .green)
            kv("available", fmt(p.vitals.diskAvailGB, "%.0f GB"))
            kv("floor", "15–25% free keeps APFS + GC healthy")
        case "memory":
            MeterRow(name: "swap",
                     value: fmt(p.vitals.swapGB, "%.1f GB"),
                     reference: "warn 8 · crit 16 GB",
                     fraction: (p.vitals.swapGB ?? 0) / 16, marker: 0.5,
                     tint: (p.vitals.swapGB ?? 0) >= 8 ? .orange : .green)
            kv("pressure", p.vitals.pressureLevel.map { "level \($0) of 4" } ?? "—")
        case "processes":
            kv("IDE processes", p.vitals.ideProcCount.map { "\($0)" } ?? "—")
            kv("ghost (>3d)", p.vitals.ghostCount.map { "\($0)" } ?? "—")
            ForEach(Array(p.ghosts.prefix(5).enumerated()), id: \.offset) { _, g in
                HStack {
                    Text(g.name).font(.system(size: 10)).lineLimit(1)
                    Spacer()
                    Text("\(g.ageSeconds / 86400)d · \(Int(g.rssMB)) MB")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
            }
        case "state":
            kv("total", fmt(p.vitals.stateTotalGB, "%.1f GB"))
            if let maxSize = p.stateDirs.first?.sizeBytes, maxSize > 0 {
                ForEach(Array(p.stateDirs.prefix(8).enumerated()), id: \.offset) { _, d in
                    MeterRow(name: d.key,
                             value: fmtBytes(d.sizeBytes),
                             reference: d.category,
                             fraction: Double(d.sizeBytes) / Double(maxSize),
                             marker: nil, tint: .blue)
                }
            }
        case "stability":
            kv("crashes (7d)", p.crashesWeekly.map { "\($0)" } ?? "—")
            kv("cpu limit", p.cpuSpeedLimit.map { "\($0)%" } ?? "—")
            kv("uptime", p.uptimeDays.map { String(format: "%.1f days", $0) } ?? "—")
        case "telemetry":
            MeterRow(name: "write rate",
                     value: fmt(p.vitals.writeMBs, "%.1f MB/s"),
                     reference: "warn 200",
                     fraction: (p.vitals.writeMBs ?? 0) / 400, marker: 0.5,
                     tint: (p.vitals.writeMBs ?? 0) >= 200 ? .orange : .green)
            kv("battery", batteryLine(p))
        case "privacy":
            ForEach(Array(p.retention.enumerated()), id: \.offset) { _, t in
                HStack {
                    Text(t.tool).font(.system(size: 11))
                    Spacer()
                    Text(t.status == "configured" && t.value != nil
                         ? "\(t.value!)d" : t.status)
                        .font(.system(size: 10))
                        .foregroundStyle(t.status == "configured"
                                         ? Color.green : Color.orange)
                }
            }
            kv("secrets scan", "opt-in — enable in config.json")
        case "work":
            if p.repos.isEmpty {
                kv("repos", "none configured — set git.repos in config.json")
            }
            ForEach(Array(p.repos.enumerated()), id: \.offset) { _, r in
                VStack(alignment: .leading, spacing: 1) {
                    Text(r.path).font(.system(size: 10)).lineLimit(1)
                    Text("\(r.uncommitted) changed · \(r.untracked) untracked · \(r.unpushed) unpushed\(r.hasRemote ? "" : " · NO REMOTE")")
                        .font(.system(size: 9)).foregroundStyle(.secondary)
                }
                .padding(.vertical, 1)
            }
        default:
            EmptyView()
        }
    }

    private var findingsBlock: some View {
        let related = model.findings(for: domain)
        return Group {
            if !related.isEmpty {
                Text("FINDINGS").font(Theme.sectionFont)
                    .foregroundStyle(.secondary)
                    .padding(.top, 10).padding(.bottom, 4)
                ForEach(Array(related.enumerated()), id: \.offset) { _, f in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(f.title).font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Theme.severityColor(f.severity))
                        if !f.recommendation.isEmpty {
                            Text("→ \(f.recommendation)")
                                .font(.system(size: 10))
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    private func kv(_ k: String, _ v: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(k).font(.system(size: 11)).foregroundStyle(.secondary)
            Spacer()
            Text(v).font(.system(size: 11))
                .multilineTextAlignment(.trailing)
        }
        .padding(.vertical, 2)
    }

    private func fmt(_ v: Double?, _ f: String) -> String {
        v.map { String(format: f, $0) } ?? "—"
    }

    private func pct(_ v: Double?) -> String {
        v.map { String(format: "%.0f%%", $0) } ?? "—"
    }

    private func fmtBytes(_ n: Int64) -> String {
        let gb = Double(n) / 1e9
        return gb >= 1 ? String(format: "%.1f GB", gb)
                       : String(format: "%.0f MB", Double(n) / 1e6)
    }

    private func batteryLine(_ p: Payload) -> String {
        guard let cycles = p.batteryCycles else { return "—" }
        let cap = p.batteryMaxPct.map { "\($0)%" } ?? "?"
        return "\(cycles) cycles · \(cap) capacity"
    }
}

struct SettingsView: View {
    @ObservedObject var model: MonitorModel
    var onAction: (String) -> Void
    @State private var launchAtLogin = SMAppServiceState.read()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button { model.showSettings = false } label: {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 11, weight: .bold))
                }
                .buttonStyle(.plain).foregroundStyle(.secondary)
                Text("SETTINGS").font(Theme.sectionFont)
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding(.bottom, 10)

            HStack {
                Text("refresh").font(.system(size: 12))
                Spacer()
                Picker("", selection: $model.refreshInterval) {
                    Text("30 s").tag(30.0)
                    Text("1 min").tag(60.0)
                    Text("5 min").tag(300.0)
                }
                .pickerStyle(.segmented)
                .frame(width: 170)
            }
            .padding(.vertical, 4)

            Toggle("launch at login", isOn: $launchAtLogin)
                .font(.system(size: 12))
                .toggleStyle(.switch)
                .controlSize(.small)
                .onChange(of: launchAtLogin) { SMAppServiceState.apply($0) }
                .padding(.vertical, 4)

            Text("thresholds & tiers live in ~/.config/wtfssd/config.json")
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .padding(.top, 6)

            HStack(spacing: 10) {
                Button("Open config") { onAction("config-open") }
                Button("Data folder") { onAction("data-open") }
                Spacer()
            }
            .font(.system(size: 11, weight: .medium))
            .buttonStyle(.plain)
            .padding(.top, 12)
        }
    }
}

/// Launch-at-login via SMAppService (macOS 13+), tolerant of failure.
enum SMAppServiceState {
    static func read() -> Bool {
        ServiceManagement.SMAppService.mainApp.status == .enabled
    }

    static func apply(_ enabled: Bool) {
        do {
            if enabled {
                try ServiceManagement.SMAppService.mainApp.register()
            } else {
                try ServiceManagement.SMAppService.mainApp.unregister()
            }
        } catch {
            // unsigned/dev builds can fail here — non-fatal
        }
    }
}
