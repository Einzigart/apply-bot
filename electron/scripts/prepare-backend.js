import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const electronDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(electronDir, "..", "dist");
const backendDir = path.join(distDir, "api-server");
const preparedDir = path.join(distDir, "prepared", "api-server");

function assertContained(realPath, root) {
  const relativePath = path.relative(root, realPath);
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    throw new Error(`Backend resource points outside ${root}: ${realPath}`);
  }
}

function assertDirectory(pathToCheck, label) {
  const stat = fs.lstatSync(pathToCheck);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`${label} must be a real directory: ${pathToCheck}`);
  }
  return fs.realpathSync(pathToCheck);
}

function assertSafeDirectoryChain(pathToCheck, root, allowMissingAtEnd = false) {
  const relativePath = path.relative(root, pathToCheck);
  assertContained(pathToCheck, root);
  let currentPath = root;
  for (const component of relativePath.split(path.sep).filter(Boolean)) {
    currentPath = path.join(currentPath, component);
    let stat;
    try {
      stat = fs.lstatSync(currentPath);
    } catch (error) {
      if (allowMissingAtEnd && error.code === "ENOENT") {
        return;
      }
      throw error;
    }
    if (stat.isSymbolicLink() || !stat.isDirectory()) {
      throw new Error(`Prepared backend path must contain real directories: ${currentPath}`);
    }
  }
}

function assertNoSymlinks(root) {
  const entries = fs.readdirSync(root, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = path.join(root, entry.name);
    if (entry.isSymbolicLink()) {
      throw new Error(`Backend resource still contains a symlink: ${entryPath}`);
    }
    if (entry.isDirectory()) {
      assertNoSymlinks(entryPath);
    }
  }
}

function copyTree(source, destination, root, ancestors = new Set()) {
  const realSource = fs.realpathSync(source);
  assertContained(realSource, root);
  const sourceStat = fs.statSync(source);
  if (sourceStat.isDirectory()) {
    if (ancestors.has(realSource)) {
      throw new Error(`Circular symlink in backend resource: ${source}`);
    }
    const nextAncestors = new Set(ancestors).add(realSource);
    fs.mkdirSync(destination, { recursive: true });
    for (const entry of fs.readdirSync(source)) {
      copyTree(path.join(source, entry), path.join(destination, entry), root, nextAncestors);
    }
    fs.chmodSync(destination, sourceStat.mode);
    return;
  }
  if (sourceStat.isFile()) {
    fs.copyFileSync(source, destination);
    fs.chmodSync(destination, sourceStat.mode);
    return;
  }
  throw new Error(`Unsupported backend resource entry: ${source}`);
}

const projectRoot = fs.realpathSync(electronDir + "/..");
const distRoot = assertDirectory(distDir, "dist");
assertContained(distRoot, projectRoot);
assertSafeDirectoryChain(path.dirname(preparedDir), distRoot, true);
assertSafeDirectoryChain(preparedDir, distRoot, true);

if (!fs.existsSync(backendDir)) {
  throw new Error(`Backend build not found at ${backendDir}`);
}

const backendRoot = assertDirectory(backendDir, "Backend build");
assertContained(backendRoot, distRoot);

function removePreparedDirSafely() {
  assertSafeDirectoryChain(path.dirname(preparedDir), distRoot, true);
  let stat;
  try {
    stat = fs.lstatSync(preparedDir);
  } catch (error) {
    if (error.code === "ENOENT") {
      return;
    }
    throw error;
  }
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`Prepared backend path must be a real directory: ${preparedDir}`);
  }
  assertSafeDirectoryChain(preparedDir, distRoot);
  fs.rmSync(preparedDir, { recursive: true, force: true });
}

removePreparedDirSafely();
fs.mkdirSync(path.dirname(preparedDir), { recursive: true });
assertSafeDirectoryChain(path.dirname(preparedDir), distRoot);
fs.mkdirSync(preparedDir);

try {
  copyTree(backendDir, preparedDir, backendRoot);
  assertNoSymlinks(preparedDir);
} catch (error) {
  try {
    removePreparedDirSafely();
  } catch (cleanupError) {
    throw new AggregateError([error, cleanupError], "Backend preparation and cleanup both failed");
  }
  throw error;
}
