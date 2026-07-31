// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "wtfssd-menubar",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "wtfssd-menubar",
            path: "Sources/wtfssd-menubar"
        )
    ]
)
