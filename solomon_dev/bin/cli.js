#!/usr/bin/env node

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execSync, spawnSync } = require('child_process');

const green = (text) => `\x1b[32m${text}\x1b[0m`;
const yellow = (text) => `\x1b[33m${text}\x1b[0m`;
const red = (text) => `\x1b[31m${text}\x1b[0m`;
const blue = (text) => `\x1b[34m${text}\x1b[0m`;
const bold = (text) => `\x1b[1m${text}\x1b[0m`;

function detectStack(dir, depth = 0) {
  if (depth > 3) return { languages: [], frameworks: [], databases: [] };

  let languages = new Set();
  let frameworks = new Set();
  let databases = new Set();

  try {
    const files = fs.readdirSync(dir);
    for (const file of files) {
      const fullPath = path.join(dir, file);
      let stat;
      try {
        stat = fs.statSync(fullPath);
      } catch (e) {
        continue;
      }

      if (stat.isDirectory()) {
        if (file !== 'node_modules' && file !== '.git' && file !== '.venv' && file !== 'venv' && file !== 'build' && file !== 'dist') {
          const sub = detectStack(fullPath, depth + 1);
          sub.languages.forEach(l => languages.add(l));
          sub.frameworks.forEach(f => frameworks.add(f));
          sub.databases.forEach(d => databases.add(d));
        }
      } else {
        if (file === 'package.json') {
          languages.add('JavaScript/TypeScript');
          try {
            const pkg = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
            const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
            if (deps['next']) frameworks.add('Next.js');
            if (deps['react']) frameworks.add('React');
            if (deps['vue']) frameworks.add('Vue');
            if (deps['@angular/core']) frameworks.add('Angular');
            if (deps['svelte']) frameworks.add('Svelte');
            if (deps['express']) frameworks.add('Express');
            if (deps['pg'] || deps['postgres']) databases.add('PostgreSQL');
            if (deps['surrealdb']) databases.add('SurrealDB');
          } catch (e) {}
        } else if (file === 'requirements.txt' || file === 'Pipfile' || file === 'poetry.lock') {
          languages.add('Python');
        } else if (file === 'pyproject.toml') {
          languages.add('Python');
          try {
            const content = fs.readFileSync(fullPath, 'utf8');
            if (content.includes('fastapi')) frameworks.add('FastAPI');
            if (content.includes('django')) frameworks.add('Django');
            if (content.includes('flask')) frameworks.add('Flask');
            if (content.includes('surrealdb')) databases.add('SurrealDB');
            if (content.includes('psycopg')) databases.add('PostgreSQL');
          } catch (e) {}
        } else if (file === 'Cargo.toml') {
          languages.add('Rust');
        } else if (file === 'go.mod') {
          languages.add('Go');
        } else if (file === 'pubspec.yaml') {
          languages.add('Dart/Flutter');
          frameworks.add('Flutter');
        } else if (file === 'pom.xml' || file === 'build.gradle') {
          languages.add('Java');
        } else if (file === 'Gemfile') {
          languages.add('Ruby');
        } else if (file.endsWith('.csproj')) {
          languages.add('C#');
        }

        if (file === 'docker-compose.yml' || file === 'docker-compose.yaml') {
          try {
            const content = fs.readFileSync(fullPath, 'utf8');
            if (content.includes('postgres')) databases.add('PostgreSQL');
            if (content.includes('surrealdb')) databases.add('SurrealDB');
            if (content.includes('mysql')) databases.add('MySQL');
            if (content.includes('redis')) databases.add('Redis');
            if (content.includes('mongodb') || content.includes('mongo:')) databases.add('MongoDB');
          } catch (e) {}
        }
      }
    }
  } catch (e) {}

  return {
    languages: Array.from(languages),
    frameworks: Array.from(frameworks),
    databases: Array.from(databases)
  };
}

function printBanner() {
  console.log(bold(blue('\n=== Solomon Harness Developer Agent Installer ===\n')));
}

function checkDependency(cmd, name) {
  try {
    execSync(cmd, { stdio: 'ignore' });
    console.log(`${green('✓')} ${name} is installed.`);
    return true;
  } catch (e) {
    console.log(`${red('✗')} ${name} is not found.`);
    return false;
  }
}

function commandExists(cmd) {
  const probe = process.platform === 'win32' ? `where ${cmd}` : `command -v ${cmd}`;
  try {
    execSync(probe, { stdio: 'ignore', shell: process.platform === 'win32' ? undefined : '/bin/sh' });
    return true;
  } catch (e) {
    return false;
  }
}

function pythonOk() {
  for (const c of ['python3', 'python']) {
    try {
      const out = execSync(`${c} --version`, { encoding: 'utf8' }).trim();
      const m = out.match(/(\d+)\.(\d+)/);
      if (m && (Number(m[1]) > 3 || (Number(m[1]) === 3 && Number(m[2]) >= 10))) return true;
    } catch (e) {}
  }
  return false;
}

function ensureUvOnPath() {
  const dirs = [path.join(os.homedir(), '.local', 'bin'), path.join(os.homedir(), '.cargo', 'bin')];
  for (const dir of dirs) {
    if (fs.existsSync(path.join(dir, 'uv')) || fs.existsSync(path.join(dir, 'uv.exe'))) {
      if (!(process.env.PATH || '').split(path.delimiter).includes(dir)) {
        process.env.PATH = `${dir}${path.delimiter}${process.env.PATH || ''}`;
      }
      return true;
    }
  }
  return false;
}

function installUv() {
  console.log(blue('  Installing uv (user-local, no sudo)...'));
  try {
    if (process.platform === 'win32') {
      execSync('powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"', { stdio: 'inherit' });
    } else {
      execSync('curl -LsSf https://astral.sh/uv/install.sh | sh', { stdio: 'inherit', shell: '/bin/sh' });
    }
  } catch (e) {
    console.log(yellow(`  Could not auto-install uv: ${e.message}`));
  }
  ensureUvOnPath();
  return commandExists('uv');
}

const INSTALL_HINTS = {
  gh: { darwin: 'brew install gh', linux: 'https://github.com/cli/cli#installation', win32: 'winget install --id GitHub.cli' },
  docker: { all: 'https://docs.docker.com/get-docker/' },
  python: { darwin: 'brew install python', linux: 'sudo apt-get install -y python3', win32: 'https://www.python.org/downloads/' },
  host: { all: 'npm i -g @anthropic-ai/claude-code   (or install the Gemini CLI)' },
};

function hint(key) {
  const h = INSTALL_HINTS[key];
  return h[process.platform] || h.all || 'see the project README';
}

// Checks the prerequisites and auto-installs the ones that are safe to install
// without sudo (uv). For the rest it prints the exact per-platform command,
// because installing them needs a package manager or elevated privileges.
function checkPrerequisites(options = {}) {
  const autoInstall = options.autoInstall !== false;
  console.log(bold(blue('Checking prerequisites...')));
  let missingRequired = 0;

  if (pythonOk()) {
    console.log(`${green('✓')} Python 3.10+`);
  } else {
    console.log(`${red('✗')} Python 3.10+ (required)  ->  ${hint('python')}`);
    missingRequired++;
  }

  if (commandExists('uv')) {
    console.log(`${green('✓')} uv`);
  } else if (autoInstall && installUv()) {
    console.log(`${green('✓')} uv (installed)`);
  } else {
    console.log(`${red('✗')} uv (required)  ->  curl -LsSf https://astral.sh/uv/install.sh | sh`);
    missingRequired++;
  }

  if (commandExists('git')) {
    console.log(`${green('✓')} git`);
  } else {
    console.log(`${red('✗')} git (required)  ->  install git for your platform`);
    missingRequired++;
  }

  if (commandExists('gh')) {
    console.log(`${green('✓')} GitHub CLI (gh)`);
  } else {
    console.log(`${yellow('!')} GitHub CLI (gh) - needed for the delivery workflows  ->  ${hint('gh')}`);
  }

  if (commandExists('claude') || commandExists('gemini')) {
    console.log(`${green('✓')} host tool (claude or gemini)`);
  } else {
    console.log(`${yellow('!')} host tool - install Claude Code or the Gemini CLI  ->  ${hint('host')}`);
  }

  if (commandExists('docker')) {
    console.log(`${green('✓')} Docker (optional)`);
  } else {
    console.log(`${yellow('!')} Docker (optional; SQLite fallback works without it)  ->  ${hint('docker')}`);
  }

  if (missingRequired > 0) {
    console.log(yellow(`\n  ${missingRequired} required prerequisite(s) still missing - install them and re-run.\n`));
  } else {
    console.log(green('  All required prerequisites are present.\n'));
  }
  return missingRequired === 0;
}

function initProject(options = {}) {
  const destDir = process.cwd();
  const pkgDir = path.join(__dirname, '..');
  const templatesSrc = path.join(pkgDir, 'templates');

  console.log(blue(`Initializing solomon-harness in: ${destDir}\n`));

  // 0. Prerequisites: check, and auto-install the ones that are safe to install.
  checkPrerequisites({ autoInstall: options.autoInstall !== false });

  // 1. Check template source exists (run sync if missing during local development)
  if (!fs.existsSync(templatesSrc)) {
    console.log(yellow('Templates directory not found in package. Running local sync...'));
    try {
      execSync('node scripts/sync-templates.js', { cwd: pkgDir, stdio: 'inherit' });
    } catch (e) {
      console.error(red(`Failed to sync templates: ${e.message}`));
      process.exit(1);
    }
  }

  // 2. Create directory structure
  console.log('Creating directories...');
  const dirs = ['.agent', 'agents'];
  dirs.forEach(d => {
    const fullPath = path.join(destDir, d);
    if (!fs.existsSync(fullPath)) {
      fs.mkdirSync(fullPath, { recursive: true });
    }
  });

  // 3. Copy Templates
  console.log('Copying agent definitions, scripts, and templates...');
  try {
    // Copy agents template
    if (fs.existsSync(path.join(templatesSrc, 'agents'))) {
      fs.cpSync(path.join(templatesSrc, 'agents'), path.join(destDir, 'agents'), { recursive: true });
    }
    // Copy .agent config
    if (fs.existsSync(path.join(templatesSrc, '.agent'))) {
      fs.cpSync(path.join(templatesSrc, '.agent'), path.join(destDir, '.agent'), { recursive: true });
    }
    // Copy docker-compose
    const composeSrc = path.join(templatesSrc, 'docker-compose.yml');
    if (fs.existsSync(composeSrc)) {
      fs.copyFileSync(composeSrc, path.join(destDir, 'docker-compose.yml'));
    }
    // Copy entire python CLI engine package
    if (fs.existsSync(path.join(templatesSrc, 'solomon_harness'))) {
      fs.cpSync(path.join(templatesSrc, 'solomon_harness'), path.join(destDir, 'solomon_harness'), { recursive: true });
    }
    // Copy project scripts
    if (fs.existsSync(path.join(templatesSrc, 'scripts'))) {
      fs.cpSync(path.join(templatesSrc, 'scripts'), path.join(destDir, 'scripts'), { recursive: true });
    }
    // Copy pyproject.toml and uv.lock if they don't already exist
    const pyprojectDest = path.join(destDir, 'pyproject.toml');
    if (!fs.existsSync(pyprojectDest)) {
      const pyprojectSrc = path.join(templatesSrc, 'pyproject.toml');
      if (fs.existsSync(pyprojectSrc)) {
        fs.copyFileSync(pyprojectSrc, pyprojectDest);
      }
    }
    const uvLockDest = path.join(destDir, 'uv.lock');
    if (!fs.existsSync(uvLockDest)) {
      const uvLockSrc = path.join(templatesSrc, 'uv.lock');
      if (fs.existsSync(uvLockSrc)) {
        fs.copyFileSync(uvLockSrc, uvLockDest);
      }
    }
  } catch (e) {
    console.error(red(`Error copying templates: ${e.message}`));
    process.exit(1);
  }

  // 3.5. Detect project tech stack and adapt config.json
  console.log('\nScanning project directories for technology stack...');
  const detected = detectStack(destDir);
  console.log(`- Languages: ${green(detected.languages.join(', ') || 'None detected')}`);
  console.log(`- Frameworks: ${green(detected.frameworks.join(', ') || 'None detected')}`);
  console.log(`- Databases: ${green(detected.databases.join(', ') || 'None detected')}`);

  // Determine active agent based on detected frameworks
  let activeAgent = 'software_engineer';
  if (detected.frameworks.includes('Flutter')) {
    activeAgent = 'flutter';
  } else if (detected.frameworks.includes('React') || detected.frameworks.includes('Next.js') || detected.frameworks.includes('Vue') || detected.frameworks.includes('Angular') || detected.frameworks.includes('Svelte')) {
    activeAgent = 'frontend';
  } else if (detected.languages.includes('Android')) {
    activeAgent = 'android';
  }

  // Update .agent/config.json
  const configPath = path.join(destDir, '.agent', 'config.json');
  if (fs.existsSync(configPath)) {
    try {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      config.tech_stack = detected;
      config.active_agent = activeAgent;
      fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
      console.log(`${green('✓')} Configuration updated with detected stack and active agent: ${bold(activeAgent)}`);
    } catch (e) {
      console.log(yellow(`Warning: Failed to update config.json with detected stack: ${e.message}`));
    }
  }

  // 4. Install Python dependencies
  console.log('\nSetting up Python virtual environment...');
  const hasUv = checkDependency('uv --version', 'uv package manager');
  if (hasUv) {
    try {
      console.log('Creating virtual environment using uv...');
      execSync('uv venv', { stdio: 'inherit' });
      
      console.log('Installing python dependencies and harness package...');
      // For local monorepo init execution:
      const parentPyproject = path.join(pkgDir, '..', 'pyproject.toml');
      if (fs.existsSync(parentPyproject)) {
        const rootPath = path.join(pkgDir, '..');
        execSync(`uv pip install -e ${rootPath}`, { stdio: 'inherit' });
      } else {
        // Fallback for independent npm package execution:
        execSync('uv pip install solomon-harness', { stdio: 'inherit' });
      }
    } catch (e) {
      console.log(yellow('Warning: Failed to install python packages via uv. You can run "uv pip install solomon-harness" manually.'));
    }
  } else {
    console.log(yellow('uv is not installed. We recommend installing uv (https://astral.sh/uv) for fast package execution.'));
  }
  
  // 5. Setup Git Hooks
  const gitDir = path.join(destDir, '.git');
  if (fs.existsSync(gitDir)) {
    console.log('\nConfiguring Git hooks...');
    const hooksDestDir = path.join(gitDir, 'hooks');
    if (!fs.existsSync(hooksDestDir)) {
      fs.mkdirSync(hooksDestDir, { recursive: true });
    }
    const hooksSrcDir = path.join(templatesSrc, 'git-hooks');
    if (fs.existsSync(hooksSrcDir)) {
      try {
        fs.readdirSync(hooksSrcDir).forEach(file => {
          if (file !== '__pycache__') {
            const srcFile = path.join(hooksSrcDir, file);
            const destFile = path.join(hooksDestDir, file);
            fs.copyFileSync(srcFile, destFile);
            fs.chmodSync(destFile, 0o755);
            console.log(`Installed ${file} hook.`);
          }
        });
        console.log(`${green('✓')} Git hooks configured successfully.`);
      } catch (e) {
        console.log(yellow(`Warning: Failed to install git hooks: ${e.message}`));
      }
    }
  }

  // 6. Automatically run compilation to generate active harnesses and IDE hooks (Claude Code / Gemini)
  console.log('\nCompiling agent harnesses and generating IDE hooks...');
  try {
    const parentPyproject = path.join(pkgDir, '..', 'pyproject.toml');
    if (fs.existsSync(parentPyproject)) {
      const rootPath = path.join(pkgDir, '..');
      execSync('uv run python -m solomon_harness.compiler', { cwd: rootPath, stdio: 'inherit' });
    } else {
      // Execute the local compiled binary
      const localBinary = path.join(destDir, '.venv', 'bin', 'solomon-harness');
      if (fs.existsSync(localBinary)) {
        execSync(`${localBinary} compile`, { cwd: destDir, stdio: 'inherit' });
      } else {
        execSync('python3 -m solomon_harness.compiler', { cwd: destDir, stdio: 'inherit' });
      }
    }
    console.log(`${green('✓')} Agent harnesses compiled and IDE hooks generated.`);
  } catch (e) {
    console.log(yellow(`Warning: Failed to compile agent harnesses: ${e.message}`));
  }

  // 7. Automatically run indexing to map project codebase into SurrealDB/SQLite database client
  console.log('\nIndexing project codebase into database...');
  try {
    const parentPyproject = path.join(pkgDir, '..', 'pyproject.toml');
    if (fs.existsSync(parentPyproject)) {
      const rootPath = path.join(pkgDir, '..');
      execSync('uv run python -m solomon_harness.cli index', { cwd: rootPath, stdio: 'inherit' });
    } else {
      const localBinary = path.join(destDir, '.venv', 'bin', 'solomon-harness');
      if (fs.existsSync(localBinary)) {
        execSync(`${localBinary} index`, { cwd: destDir, stdio: 'inherit' });
      } else {
        execSync('python3 -m solomon_harness.cli index', { cwd: destDir, stdio: 'inherit' });
      }
    }
    console.log(`${green('✓')} Codebase indexed successfully.`);
  } catch (e) {
    console.log(yellow(`Warning: Failed to index codebase: ${e.message}`));
  }

  console.log(green('\n✓ solomon-harness initialized successfully!'));
  console.log('\nNext steps:');
  console.log(`1. Run ${bold('docker compose up -d')} to start the SurrealDB memory service (optional; SQLite is the fallback).`);
  console.log(`2. Drive delivery with the workflows in Claude Code or the Gemini CLI: ${bold('/solomon-dev-issue')}, ${bold('/solomon-dev-start')}, ${bold('/solomon-dev-review')}, ${bold('/solomon-dev-release')}.`);
  console.log(`   Or run them headless: ${bold('solomon-dev <stage>')} (stages: idea, issue, bug, refine, start, review, release).`);
}

// Headless workflow stages, mirroring the .claude/commands/solomon-dev-*.md files.
const STAGES = ['idea', 'issue', 'bug', 'refine', 'start', 'review', 'release'];

function buildPrompt(stage, args) {
  const cmdFile = path.join(process.cwd(), '.claude', 'commands', `solomon-dev-${stage}.md`);
  if (!fs.existsSync(cmdFile)) {
    console.error(red(`Command file not found: ${cmdFile}. Run 'solomon-dev init' first.`));
    process.exit(1);
  }
  let text = fs.readFileSync(cmdFile, 'utf8');
  // Strip the YAML frontmatter; keep only the prompt body.
  if (text.startsWith('---')) {
    text = text.split('---').slice(2).join('---').trim();
  }
  return text.split('$ARGUMENTS').join(args.join(' '));
}

function runWorkflow(stage, args) {
  const engine = (process.env.SOLOMON_ENGINE || 'claude').toLowerCase();
  if (engine !== 'claude' && engine !== 'gemini') {
    console.error(red(`Unknown SOLOMON_ENGINE '${engine}'. Use 'claude' or 'gemini'.`));
    process.exit(1);
  }
  const prompt = buildPrompt(stage, args);
  console.log(blue(`Running /solomon-dev-${stage} headless via ${engine}...`));

  // Both CLIs run a single non-interactive prompt with -p and read it from stdin.
  const res = spawnSync(engine, ['-p'], { input: prompt, stdio: ['pipe', 'inherit', 'inherit'] });
  if (res.error) {
    console.error(red(`Failed to launch '${engine}': ${res.error.message}. Is it installed and authenticated?`));
    process.exit(1);
  }
  process.exit(res.status || 0);
}

function printUsage() {
  console.log('Usage:');
  console.log('  solomon-dev init [--no-install]   Install the harness into this project');
  console.log('  solomon-dev doctor [--no-install] Check (and install) prerequisites');
  console.log('  solomon-dev <stage> [args]       Run a delivery workflow headlessly');
  console.log(`  stages: ${STAGES.join(', ')}`);
  console.log('  engine: set SOLOMON_ENGINE=claude|gemini (default claude)');
  console.log('  --no-install: only report missing prerequisites, do not install');
}

function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'init';
  const autoInstall = !args.includes('--no-install');

  if (command === 'init') {
    printBanner();
    initProject({ autoInstall });
  } else if (command === 'doctor') {
    printBanner();
    checkPrerequisites({ autoInstall });
  } else if (STAGES.includes(command)) {
    runWorkflow(command, args.slice(1));
  } else if (command === 'help' || command === '--help' || command === '-h') {
    printBanner();
    printUsage();
  } else {
    console.log(red(`Unknown command: ${command}`));
    printUsage();
    process.exit(1);
  }
}

main();
