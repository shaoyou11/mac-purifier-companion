"""Sign and publish an appcast for an already published, verified GitHub release."""
import argparse
from datetime import datetime, timezone
from email.utils import format_datetime
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import xml.etree.ElementTree as ET

REPO = "shaoyou11/mac-purifier-companion"
SPARKLE = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def run(*args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed; command output withheld")
    return result.stdout.strip()


def publish(app: Path, archive: Path, tag: str, tools: Path):
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root:
        raise ValueError("Run this command from the repository root")
    user = json.loads(run("gh", "api", "user"))
    assert user["login"] == "shaoyou11", "Unexpected GitHub account"
    assert run("git", "branch", "--show-current") == "main"
    assert not run("git", "status", "--porcelain"), "Commit source changes before publishing the feed"
    remote = run("git", "remote", "get-url", "origin").removesuffix(".git")
    assert remote.endswith("/" + REPO) or remote.endswith(":" + REPO)
    release = json.loads(run("gh", "api", f"repos/{REPO}/releases/tags/{tag}"))
    assert not release["draft"]
    asset = next(a for a in release["assets"] if a["name"] == archive.name)
    assert asset["size"] == archive.stat().st_size
    assert asset["digest"] == "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert "v" + info["MacFanLinkDistribution"] == tag
    config = json.loads((root / "Resources/updater.json").read_text())
    assert info["SUPublicEDKey"] == config["publicKey"]
    assert run(tools / "generate_keys", "--account", config["keychainAccount"], "-p") == config["publicKey"]
    feed = root / "appcast.xml"
    if feed.exists():
        previous = ET.parse(feed).find(f"./channel/item/{{{SPARKLE}}}version")
        assert previous is None or int(info["CFBundleVersion"]) > int(previous.text), "Build number must increase"
    signature = run(tools / "sign_update", "--account", config["keychainAccount"], "-p", archive)
    run(tools / "sign_update", "--account", config["keychainAccount"], "--verify", archive, signature)
    ET.register_namespace("sparkle", SPARKLE)
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Mac 净化器伴侣 · 个性化版本"
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = tag
    ET.SubElement(item, "pubDate").text = format_datetime(datetime.now(timezone.utc))
    ET.SubElement(item, f"{{{SPARKLE}}}version").text = info["CFBundleVersion"]
    ET.SubElement(item, f"{{{SPARKLE}}}shortVersionString").text = info["MacFanLinkDistribution"]
    ET.SubElement(item, f"{{{SPARKLE}}}minimumSystemVersion").text = info["LSMinimumSystemVersion"]
    ET.SubElement(item, "description").text = "新版已发布。安装后将自动重新启动，保留现有设置。"
    ET.SubElement(item, "enclosure", {"url": asset["browser_download_url"], "length": str(asset["size"]),
                  "type": "application/octet-stream", f"{{{SPARKLE}}}edSignature": signature})
    ET.indent(rss)
    ET.ElementTree(rss).write(feed, encoding="utf-8", xml_declaration=True)
    run(tools / "sign_update", "--account", config["keychainAccount"], feed)
    run(tools / "sign_update", "--account", config["keychainAccount"], "--verify", feed)
    run("git", "add", "appcast.xml")
    run("git", "-c", "user.name=shaoyou11", "-c", f"user.email={user['id']}+shaoyou11@users.noreply.github.com",
        "commit", "-m", f"发布：更新签名订阅至 {tag}", "-m", "安装包摘要与签名已核验，仅发布有效安装包的更新条目。")
    run("git", "push", "origin", "HEAD:main")
    print("Signed update feed published")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sparkle-bin", type=Path, required=True)
    args = parser.parse_args()
    publish(args.app, args.archive, args.tag, args.sparkle_bin)
