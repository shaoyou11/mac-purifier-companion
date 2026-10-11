"""Embed the pinned Sparkle framework and configure update verification."""
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess


def embed(app: Path, artifacts: Path, identity: str = "-") -> None:
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "Resources/updater.json").read_text())
    framework = artifacts / "Sparkle.xcframework/macos-arm64_x86_64/Sparkle.framework"
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(framework)], check=True)
    destination = app / "Contents/Frameworks/Sparkle.framework"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(framework, destination, symlinks=True)  # Fail rather than overwrite.
    if identity != "-":
        base = destination / "Versions/B"
        nested = list((base / "XPCServices").glob("*.xpc")) + [base / "Autoupdate", base / "Updater.app", destination]
        for item in nested:
            subprocess.run(["codesign", "--force", "--options", "runtime", "--timestamp", "--sign", identity, str(item)], check=True)
    notices = app / "Contents/Resources/licenses/Sparkle"
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copy2(artifacts / "LICENSE", notices / "LICENSE")
    info_path = app / "Contents/Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info.update(SUFeedURL=config["feedURL"], SUPublicEDKey=config["publicKey"],
                SUEnableAutomaticChecks=True, SUAutomaticallyUpdate=False,
                SUAllowsAutomaticUpdates=False, SUUpdateCheckInterval=21600,
                SUVerifyUpdateBeforeExtraction=True, SURequireSignedFeed=True,
                SUEnableSystemProfiling=False)
    info_path.write_bytes(plistlib.dumps(info))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--identity", default="-")
    args = parser.parse_args()
    embed(args.app, args.artifacts, args.identity)
