// PopoverView.swift — the dropdown UI. Modeled on modern monitor widgets:
// dark card, hero metric, small-caps sections, right-aligned values.

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
    @Published var payload: Payload?
    @Published var lastError = false
}

struct PopoverView: View {
    @ObservedObject var model: MonitorModel
    var onRefresh: () -> Void
    var onAction: (String) -> Void   // "scan" | "digest"
    var onQuit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if let payload = model.payload {
                hero(payload)
                vitals(payload)
                section("DOMAINS")
                ForEach(Array(payload.domains.enumerated()), id: \.offset) { _, d in
                    HStack {
                        Circle().fill(Theme.statusColor(d.status))
                            .frame(width: 7, height: 7)
                        Text(d.name).font(.system(size: 12))
                        Spacer()
                        Text(d.status).font(Theme.valueFont)
                            .foregroundStyle(Theme.statusColor(d.status))
                    }
                    .padding(.vertical, 2.5)
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
                     ? "scan failed — is ssdwtf installed?"
                     : "scanning…")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 30)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            footer
        }
        .padding(14)
        .frame(width: 292)
        .background(.ultraThinMaterial)
    }

    private var header: some View {
        HStack {
            Text("SSDWTF MONITOR").font(Theme.sectionFont)
                .foregroundStyle(.secondary)
            Spacer()
            Button(action: onRefresh) {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
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
        .padding(.bottom, 8)
    }

    private func vitals(_ payload: Payload) -> some View {
        VStack(alignment: .leading, spacing: 2.5) {
            section("VITALS")
            vitalRow("swap", value: payload.vitals.swapGB.map { String(format: "%.1f GB", $0) },
                     bad: (payload.vitals.swapGB ?? 0) >= 8)
            vitalRow("disk free", value: payload.vitals.diskFreePct.map { String(format: "%.0f%%", $0) },
                     bad: (payload.vitals.diskFreePct ?? 100) < 15)
            vitalRow("write rate", value: payload.vitals.writeMBs.map { String(format: "%.1f MB/s", $0) },
                     bad: (payload.vitals.writeMBs ?? 0) >= 200)
            vitalRow("mem pressure", value: payload.vitals.pressureLevel.map { "level \($0)" },
                     bad: (payload.vitals.pressureLevel ?? 1) >= 2)
        }
        .padding(.bottom, 2)
    }

    private func vitalRow(_ name: String, value: String?, bad: Bool) -> some View {
        HStack {
            Text(name).font(.system(size: 12))
            Spacer()
            Text(value ?? "—").font(Theme.valueFont)
                .foregroundStyle(value == nil ? Color.gray
                                : (bad ? Color.orange : Color.primary))
        }
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
