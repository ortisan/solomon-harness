const fs = require('fs');
const path = require('path');

const rootDir = path.join(__dirname, '../..');
const solomonDevDir = path.join(__dirname, '..');
const destTemplates = path.join(solomonDevDir, 'templates');

console.log('Syncing templates from workspace root to npm package...');

// Clean and recreate target templates directory
if (fs.existsSync(destTemplates)) {
  fs.rmSync(destTemplates, { recursive: true, force: true });
}
fs.mkdirSync(destTemplates, { recursive: true });

// Helper to filter files to keep the package light
function copyFiltered(src, dest) {
  fs.cpSync(src, dest, {
    recursive: true,
    filter: (srcPath) => {
      const base = path.basename(srcPath);
      // Exclude temporary, cache and compiled directories we don't want to package
      if (base === '__pycache__' || base === '.git' || base === '.pytest_cache' || base === '.venv') {
        return false;
      }
      return true;
    }
  });
}

// Copy agents/
if (fs.existsSync(path.join(rootDir, 'agents'))) {
  copyFiltered(path.join(rootDir, 'agents'), path.join(destTemplates, 'agents'));
}

// Copy .agent/config.json
const agentConfigDir = path.join(destTemplates, '.agent');
fs.mkdirSync(agentConfigDir, { recursive: true });
fs.copyFileSync(path.join(rootDir, '.agent', 'config.json'), path.join(agentConfigDir, 'config.json'));

// Copy docker-compose.yml
fs.copyFileSync(path.join(rootDir, 'docker-compose.yml'), path.join(destTemplates, 'docker-compose.yml'));

// Copy scripts/git-hooks/
if (fs.existsSync(path.join(rootDir, 'scripts', 'git-hooks'))) {
  copyFiltered(path.join(rootDir, 'scripts', 'git-hooks'), path.join(destTemplates, 'git-hooks'));
}

// Copy the entire python CLI engine package
if (fs.existsSync(path.join(rootDir, 'solomon_harness'))) {
  copyFiltered(path.join(rootDir, 'solomon_harness'), path.join(destTemplates, 'solomon_harness'));
}

// Copy the scripts/ folder containing validators, syncers, etc.
if (fs.existsSync(path.join(rootDir, 'scripts'))) {
  copyFiltered(path.join(rootDir, 'scripts'), path.join(destTemplates, 'scripts'));
}

// Copy pyproject.toml and uv.lock so the user has the complete runnable python layout
fs.copyFileSync(path.join(rootDir, 'pyproject.toml'), path.join(destTemplates, 'pyproject.toml'));
if (fs.existsSync(path.join(rootDir, 'uv.lock'))) {
  fs.copyFileSync(path.join(rootDir, 'uv.lock'), path.join(destTemplates, 'uv.lock'));
}

console.log('Templates synced successfully to solomon-dev/templates/');
