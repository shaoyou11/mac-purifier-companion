// swift-tools-version: 6.3
import PackageDescription

let package = Package(
    name: "MacFanLink",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "MacFanLink", targets: ["MacFanLink"]),
        .executable(name: "FanHelper", targets: ["FanHelper"])
    ],
    dependencies: [
        .package(url: "https://github.com/sparkle-project/Sparkle", exact: "2.10.0")
    ],
    targets: [
        .executableTarget(
            name: "MacFanLink",
            dependencies: ["FanControlProtocol", .product(name: "Sparkle", package: "Sparkle")],
            swiftSettings: [.defaultIsolation(MainActor.self)],
            linkerSettings: [.unsafeFlags(["-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks"])]
        ),
        .target(name: "FanControlProtocol"),
        .executableTarget(name: "FanHelper", dependencies: ["FanControlProtocol"]),
        .testTarget(name: "FanHelperTests", dependencies: ["FanHelper"], path: "tests/FanHelperTests")
    ]
)
