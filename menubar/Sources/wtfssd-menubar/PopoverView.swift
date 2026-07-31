// PopoverView.swift — the main card: hero, vitals with meter bars,
// clickable domain rows, footer. Detail and settings views live in
// DetailViews.swift.

import SwiftUI

enum Theme {
    static func statusColor(_ status: String) -> Color {
        switch status {
        case "critical": return .red
        case "warn": return .orange
        case "ok": return .green
        default: return .gray
        }
    }

    static let severityRank = ["critical": 2, "warn": 1, "info": 0]

    static func severityColor(_ severity: String) -> Color {
        switch severity {
        case "critical": return .red
        case "warn": return .orange
        default: return Color(.secondaryLabelColor)
        }
    }

    static let sectionFont = Font.system(size: 10, weight: .semibold)
    static let valueFont = Font.system(size: 12, weight: .medium).monospacedDigit()
}

final class MonitorModel: ObservableObject {
    @Published var payload: Payload?        // fast tier (title/hero/vitals)
    @Published var fullPayload: Payload?    // full tier (detail views)
    @Published var lastError = false
    @Published var selectedDomain: String?
    @Published var showSettings = false
    @Published var refreshInterval: Double {
        didSet { UserDefaults.standard.set(refreshInterval, forKey: "refreshInterval") }
    }

    init() {
        let saved = UserDefaults.standard.double(forKey: "refreshInterval")
        refreshInterval = saved > 0 ? saved : 60
    }

    /// Best available payload for detail rendering (full preferred).
    var detailPayload: Payload? { fullPayload ?? payload }

    func findings(for domain: String) -> [Finding] {
        let prefixes: [String]
        switch domain {
        case "drive": prefixes = ["smart."]
        case "backup": prefixes = ["backup."]
        case "headroom": prefixes = ["disk.", "apfs."]
        case "memory": prefixes = ["swap.", "pressure.", "memory."]
        case "processes": prefixes = ["procs.", "mcp."]
        case "state": prefixes = ["state.", "logs."]
        case "stability": prefixes = ["crashes.", "thermal.", "uptime.",
                                     "launchd.", "spotlight."]
        case "telemetry": prefixes = ["writerate.", "battery."]
        case "privacy": prefixes = ["secrets.", "retention."]
        case "work": prefixes = ["work."]
        default: prefixes = []
        }
        return (detailPayload?.findings ?? []).filter { f in
            prefixes.contains(where: { f.code.hasPrefix($0) })
        }
    }
}

struct PopoverView: View {
    @ObservedObject var model: MonitorModel
    var onRefresh: () -> Void
    var onAction: (String) -> Void   // "scan" | "digest"
    var onQuit: () -> Void

    var body: some View {
        Group {
            if model.showSettings {
                SettingsView(model: model, onAction: onAction)
            } else if let domain = model.selectedDomain {
                DomainDetailView(domain: domain, model: model)
            } else {
                mainCard
            }
        }
        .padding(14)
        .frame(width: 300)
        .background(.ultraThinMaterial)
    }

    // MARK: main card

    private var mainCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if let payload = model.payload {
                hero(payload)
                vitals(payload)
                section("DOMAINS")
                ForEach(Array(payload.domains.enumerated()), id: \.offset) { _, d in
                    Button { model.selectedDomain = d.name } label: {
                        HStack {
                            Circle().fill(Theme.statusColor(d.status))
                                .frame(width: 7, height: 7)
                            Text(d.name).font(.system(size: 12))
                                .foregroundStyle(.primary)
                            Spacer()
                            Text(d.status).font(Theme.valueFont)
                                .foregroundStyle(Theme.statusColor(d.status))
                            Image(systemName: "chevron.right")
                                .font(.system(size: 8, weight: .bold))
                                .foregroundStyle(.tertiary)
                        }
                        .padding(.vertical, 2.5)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
                let top = topFindings(payload)
                if !top.isEmpty {
                    section("FINDINGS")
                    ForEach(Array(top.enumerated()), id: \.offset) { _, f in
                        HStack(alignment: .firstTextBaseline) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 9))
                                .foregroundStyle(Theme.severityColor(f.severity))
                            Text(f.title)
                                .font(.system(size: 11))
                                .lineLimit(2)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer()
                        }
                        .padding(.vertical, 2)
                    }
                }
            } else {
                Text(model.lastError
                     ? "scan failed — is wtfssd installed?"
                     : "scanning…")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 30)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            footer
        }
    }

    private var header: some View {
        HStack {
            Text("WTFSSD MONITOR").font(Theme.sectionFont)
                .foregroundStyle(.secondary)
            Spacer()
            Button { model.showSettings = true } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.plain).foregroundStyle(.secondary)
            Button(action: onRefresh) {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.plain).foregroundStyle(.secondary)
        }
        .padding(.bottom, 10)
    }

    private func hero(_ payload: Payload) -> some View {
        let worst = worstSeverity(payload)
        return HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("\(payload.score)")
                .font(.system(size: 34, weight: .bold).monospacedDigit())
                .foregroundStyle(Theme.statusColor(worst))
            Text(payload.grade)
                .font(.system(size: 15, weight: .semibold))
                .padding(.horizontal, 7).padding(.vertical, 2)
                .background(Theme.statusColor(worst).opacity(0.18))
                .foregroundStyle(Theme.statusColor(worst))
                .clipShape(RoundedRectangle(cornerRadius: 5))
            Spacer()
            Text(payload.scannedAt.replacingOccurrences(of: "T", with: " "))
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
        }
        .padding(.bottom, 4)
    }

    // MARK: vitals with meter bars (value + reference point)

    private func vitals(_ payload: Payload) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            section("VITALS")
            if let pct = payload.vitals.smartPercentUsed {
                MeterRow(name: "SSD wear",
                         value: "\(pct)%", reference: "of rated life",
                         fraction: Double(pct) / 100, marker: nil,
                         tint: pct >= 90 ? .red : (pct >= 50 ? .orange : .green))
            }
            MeterRow(name: "swap",
                     value: fmt(payload.vitals.swapGB, "%.1f GB"),
                     reference: "crit \(Int(16)) GB",
                     fraction: (payload.vitals.swapGB ?? 0) / 16,
                     marker: 8.0 / 16.0,
                     tint: (payload.vitals.swapGB ?? 0) >= 16 ? .red
                           : ((payload.vitals.swapGB ?? 0) >= 8 ? .orange : .green))
            MeterRow(name: "disk free",
                     value: fmt(payload.vitals.diskFreePct, "%.0f%%"),
                     reference: "of \(fmt(payload.vitals.diskSizeGB, "%.0f GB"))",
                     fraction: (payload.vitals.diskFreePct ?? 100) / 100,
                     marker: 0.15,
                     tint: (payload.vitals.diskFreePct ?? 100) < 10 ? .red
                           : ((payload.vitals.diskFreePct ?? 100) < 15 ? .orange : .green))
            MeterRow(name: "write rate",
                     value: fmt(payload.vitals.writeMBs, "%.1f MB/s"),
                     reference: "warn 200",
                     fraction: (payload.vitals.writeMBs ?? 0) / 400,
                     marker: 0.5,
                     tint: (payload.vitals.writeMBs ?? 0) >= 200 ? .orange : .green)
            MeterRow(name: "mem pressure",
                     value: payload.vitals.pressureLevel.map { "level \($0)" } ?? "—",
                     reference: "of 4",
                     fraction: Double(payload.vitals.pressureLevel ?? 1) / 4,
                     marker: 0.5,
                     tint: (payload.vitals.pressureLevel ?? 1) >= 4 ? .red
                           : ((payload.vitals.pressureLevel ?? 1) >= 2 ? .orange : .green))
        }
    }

    private func fmt(_ v: Double?, _ format: String) -> String {
        v.map { String(format: format, $0) } ?? "—"
    }

    private func section(_ title: String) -> some View {
        Text(title).font(Theme.sectionFont)
            .foregroundStyle(.secondary)
            .padding(.top, 10)
            .padding(.bottom, 4)
    }

    private var footer: some View {
        HStack(spacing: 10) {
            Button("Full Scan") { onAction("scan") }
            Button("Digest") { onAction("digest") }
            Spacer()
            Button("Quit", action: onQuit)
                .foregroundStyle(.secondary)
        }
        .font(.system(size: 11, weight: .medium))
        .buttonStyle(.plain)
        .padding(.top, 12)
    }

    private func worstSeverity(_ p: Payload) -> String {
        p.findings.reduce("ok") { w, f in
            Theme.severityRank[f.severity, default: 0]
                > Theme.severityRank[w, default: 0] ? f.severity : w
        }
    }

    private func topFindings(_ p: Payload) -> [Finding] {
        Array(p.findings.sorted {
            Theme.severityRank[$0.severity, default: 0]
                > Theme.severityRank[$1.severity, default: 0]
        }.prefix(4))
    }
}

/// A labeled meter: name, thin bar with optional threshold marker, and a
/// value + reference so the number always has context.
struct MeterRow: View {
    let name: String
    let value: String
    let reference: String
    let fraction: Double
    let marker: Double?
    let tint: Color

    var body: some View {
        VStack(spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
                Text(name).font(.system(size: 12))
                Spacer()
                Text(value).font(Theme.valueFont).foregroundStyle(tint)
                Text(reference).font(.system(size: 9))
                    .foregroundStyle(.secondary)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.primary.opacity(0.10))
                    Capsule().fill(tint.opacity(0.85))
                        .frame(width: max(2, geo.size.width * min(1, max(0, fraction))))
                    if let marker {
                        Rectangle().fill(Color.primary.opacity(0.45))
                            .frame(width: 1.5)
                            .offset(x: geo.size.width * min(1, max(0, marker)) - 0.75)
                    }
                }
            }
            .frame(height: 4)
        }
    }
}
