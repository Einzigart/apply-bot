import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const electronDir = path.join(__dirname, "..");
const distDir = path.join(electronDir, "node_modules", "electron", "dist");

if (process.platform === "darwin" && fs.existsSync(distDir)) {
  const oldApp = path.join(distDir, "Electron.app");
  const newApp = path.join(distDir, "Apply Bot.app");

  if (fs.existsSync(oldApp) && !fs.existsSync(newApp)) {
    fs.renameSync(oldApp, newApp);
  }

  const appToUse = fs.existsSync(newApp) ? newApp : oldApp;
  const execDir = path.join(appToUse, "Contents", "MacOS");
  const oldExec = path.join(execDir, "Electron");
  const newExec = path.join(execDir, "Apply Bot");

  if (fs.existsSync(oldExec) && !fs.existsSync(newExec)) {
    fs.renameSync(oldExec, newExec);
  }

  const plistPath = path.join(appToUse, "Contents", "Info.plist");
  if (fs.existsSync(plistPath)) {
    let content = fs.readFileSync(plistPath, "utf-8");
    content = content.replace(/<key>CFBundleDisplayName<\/key>\s*<string>[^<]*<\/string>/, "<key>CFBundleDisplayName</key>\n\t<string>Apply Bot</string>");
    content = content.replace(/<key>CFBundleName<\/key>\s*<string>[^<]*<\/string>/, "<key>CFBundleName</key>\n\t<string>Apply Bot</string>");
    content = content.replace(/<key>CFBundleExecutable<\/key>\s*<string>[^<]*<\/string>/, "<key>CFBundleExecutable</key>\n\t<string>Apply Bot</string>");
    fs.writeFileSync(plistPath, content, "utf-8");
  }

  const icnsSource = path.join(electronDir, "assets", "icon.icns");
  const icnsTarget = path.join(appToUse, "Contents", "Resources", "electron.icns");
  if (fs.existsSync(icnsSource) && fs.existsSync(path.dirname(icnsTarget))) {
    fs.copyFileSync(icnsSource, icnsTarget);
  }

  const pathTxt = path.join(electronDir, "node_modules", "electron", "path.txt");
  if (fs.existsSync(newApp)) {
    fs.writeFileSync(pathTxt, "Apply Bot.app/Contents/MacOS/Apply Bot", "utf-8");
  }
}
