import AppKit
import Combine
import Sparkle
import SwiftUI

@MainActor
final class AppUpdater: ObservableObject {
    static let shared = AppUpdater()
    @Published private(set) var canCheckForUpdates = false
    @Published private(set) var automaticallyChecks = false
    private let controller: SPUStandardUpdaterController
    private var started = false

    private init() {
        controller = SPUStandardUpdaterController(startingUpdater: false, updaterDelegate: nil, userDriverDelegate: nil)
        controller.updater.publisher(for: \.canCheckForUpdates).assign(to: &$canCheckForUpdates)
        controller.updater.publisher(for: \.automaticallyChecksForUpdates).assign(to: &$automaticallyChecks)
    }

    func start() {
        guard !started, Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") != nil else { return }
        started = true
        controller.startUpdater()
        if controller.updater.automaticallyChecksForUpdates {
            controller.updater.checkForUpdatesInBackground()
        }
    }

    func check() {
        NSApp.activate(ignoringOtherApps: true)
        controller.checkForUpdates(nil)
    }

    func setAutomaticChecks(_ enabled: Bool) {
        controller.updater.automaticallyChecksForUpdates = enabled
    }
}

struct CheckForAppUpdatesButton: View {
    @ObservedObject private var updater = AppUpdater.shared
    var body: some View {
        Button("检查更新…") { updater.check() }
            .disabled(!updater.canCheckForUpdates)
    }
}

struct AppUpdateSettings: View {
    @ObservedObject private var updater = AppUpdater.shared
    private var version: String {
        Bundle.main.object(forInfoDictionaryKey: "MacFanLinkDistribution") as? String
            ?? Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
    }
    var body: some View {
        ContentSection(title: "软件更新", subtitle: "从你的 GitHub 发布版本获取更新。") {
            LabeledContent("当前版本", value: version)
            Toggle("自动检查新版本", isOn: Binding(get: { updater.automaticallyChecks }, set: updater.setAutomaticChecks))
            HStack {
                Text("发现新版后提示；经你确认，下载并替换应用、重新启动。")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                CheckForAppUpdatesButton()
            }
        }
    }
}
