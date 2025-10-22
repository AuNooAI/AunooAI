#!/usr/bin/env python
"""
PostgreSQL Setup Script for AunooAI

This script automates PostgreSQL setup for new installations:
1. Detects if PostgreSQL is installed
2. Installs PostgreSQL if needed (Linux only)
3. Creates database and user
4. Runs migrations
5. Updates .env configuration

Usage:
    python scripts/setup_postgresql.py [--skip-install] [--force]

Options:
    --skip-install    Skip PostgreSQL installation, only setup database
    --force          Force recreation of database (WARNING: destroys existing data)
"""

import os
import sys
import subprocess
import logging
import secrets
import string
from pathlib import Path
import argparse
from urllib.parse import quote_plus

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def detect_os():
    """Detect operating system."""
    if sys.platform.startswith('linux'):
        # Detect Linux distribution
        try:
            with open('/etc/os-release') as f:
                os_info = f.read().lower()
                if 'ubuntu' in os_info or 'debian' in os_info:
                    return 'debian'
                elif 'centos' in os_info or 'rhel' in os_info or 'fedora' in os_info:
                    return 'redhat'
        except FileNotFoundError:
            pass
        return 'linux'
    elif sys.platform == 'darwin':
        return 'macos'
    elif sys.platform == 'win32':
        return 'windows'
    return 'unknown'


def check_postgresql_installed():
    """Check if PostgreSQL is installed."""
    try:
        result = subprocess.run(
            ['psql', '--version'],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            logger.info(f"✅ PostgreSQL found: {version}")
            return True
    except FileNotFoundError:
        pass

    logger.warning("❌ PostgreSQL not found")
    return False


def install_postgresql_debian():
    """Install PostgreSQL on Debian/Ubuntu with pgvector extension."""
    logger.info("Installing PostgreSQL on Debian/Ubuntu...")

    commands = [
        ['sudo', 'apt-get', 'update'],
        ['sudo', 'apt-get', 'install', '-y', 'postgresql', 'postgresql-contrib', 'postgresql-16-pgvector'],
        ['sudo', 'systemctl', 'start', 'postgresql'],
        ['sudo', 'systemctl', 'enable', 'postgresql']
    ]

    for cmd in commands:
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            logger.error(f"Command failed: {' '.join(cmd)}")
            return False

    logger.info("✅ PostgreSQL installed successfully")
    return True


def install_postgresql_redhat():
    """Install PostgreSQL on RedHat/CentOS/Fedora with pgvector extension."""
    logger.info("Installing PostgreSQL on RedHat/CentOS/Fedora...")

    commands = [
        ['sudo', 'dnf', 'install', '-y', 'postgresql-server', 'postgresql-contrib', 'pgvector'],
        ['sudo', 'postgresql-setup', '--initdb'],
        ['sudo', 'systemctl', 'start', 'postgresql'],
        ['sudo', 'systemctl', 'enable', 'postgresql']
    ]

    for cmd in commands:
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            logger.error(f"Command failed: {' '.join(cmd)}")
            return False

    logger.info("✅ PostgreSQL installed successfully")
    return True


def install_postgresql_macos():
    """Install PostgreSQL on macOS using Homebrew with pgvector extension."""
    logger.info("Installing PostgreSQL on macOS...")

    # Check if Homebrew is installed
    try:
        subprocess.run(['brew', '--version'], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.error("❌ Homebrew not found. Please install Homebrew first: https://brew.sh")
        return False

    commands = [
        ['brew', 'install', 'postgresql@14'],
        ['brew', 'install', 'pgvector'],
        ['brew', 'services', 'start', 'postgresql@14']
    ]

    for cmd in commands:
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            logger.error(f"Command failed: {' '.join(cmd)}")
            return False

    logger.info("✅ PostgreSQL installed successfully")
    return True


def install_postgresql():
    """Install PostgreSQL based on operating system."""
    os_type = detect_os()

    logger.info(f"Detected OS: {os_type}")

    if os_type == 'debian':
        return install_postgresql_debian()
    elif os_type == 'redhat':
        return install_postgresql_redhat()
    elif os_type == 'macos':
        return install_postgresql_macos()
    elif os_type == 'windows':
        logger.error("Windows automatic installation not supported.")
        logger.info("Please download PostgreSQL from: https://www.postgresql.org/download/windows/")
        return False
    else:
        logger.error(f"Unsupported operating system: {os_type}")
        return False


def generate_password(length=32):
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "+/="
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def sanitize_db_name(tenant_name):
    """Create PostgreSQL database name from tenant name."""
    db_name = tenant_name.replace('.aunoo.ai', '').replace('.', '_').replace('-', '_')
    if db_name[0].isdigit():
        db_name = 'db_' + db_name
    return db_name[:63]  # PostgreSQL max identifier length


def get_tenant_name_from_cwd():
    """Get tenant name from current working directory."""
    cwd = Path.cwd()
    # Check if we're in a tenant directory under /home/orochford/tenants/
    if '/home/orochford/tenants/' in str(cwd):
        # Extract domain from path (e.g., /home/orochford/tenants/skunkworkx.aunoo.ai)
        parts = str(cwd).split('/home/orochford/tenants/')
        if len(parts) > 1:
            domain = parts[1].split('/')[0]  # Get first part after tenants/
            return domain
    return None


def create_database_and_user(db_name=None, db_user=None, db_password=None, force=False):
    """Create PostgreSQL database and user."""

    # Auto-detect tenant name if db_name not provided
    if db_name is None:
        tenant_name = get_tenant_name_from_cwd()
        if tenant_name:
            db_name = sanitize_db_name(tenant_name)
            logger.info(f"Auto-detected tenant: {tenant_name} → database: {db_name}")
        else:
            db_name = 'aunoo_db'
            logger.warning(f"Could not detect tenant name, using default: {db_name}")

    # Auto-generate user name if not provided
    if db_user is None:
        db_user = f"{db_name}_user"

    if db_password is None:
        db_password = generate_password()

    logger.info(f"Creating database '{db_name}' and user '{db_user}'...")

    # Drop database if force flag is set
    if force:
        logger.warning(f"⚠️  FORCE mode: Dropping existing database '{db_name}'...")
        drop_cmd = f"DROP DATABASE IF EXISTS {db_name};"
        result = subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c', drop_cmd],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            logger.info(f"✅ Dropped database '{db_name}'")

    # Create user
    create_user_cmd = f"CREATE USER {db_user} WITH PASSWORD '{db_password}';"
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-c', create_user_cmd],
        capture_output=True,
        text=True,
        check=False
    )

    # Ignore error if user already exists
    if result.returncode != 0 and 'already exists' not in result.stderr:
        logger.error(f"Failed to create user: {result.stderr}")
        return None
    elif 'already exists' in result.stderr:
        logger.info(f"User '{db_user}' already exists")
        # Update password for existing user
        alter_user_cmd = f"ALTER USER {db_user} WITH PASSWORD '{db_password}';"
        subprocess.run(
            ['sudo', '-u', 'postgres', 'psql', '-c', alter_user_cmd],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"Updated password for user '{db_user}'")
    else:
        logger.info(f"✅ Created user '{db_user}'")

    # Create database
    create_db_cmd = f"CREATE DATABASE {db_name} OWNER {db_user};"
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-c', create_db_cmd],
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode != 0 and 'already exists' not in result.stderr:
        logger.error(f"Failed to create database: {result.stderr}")
        return None
    elif 'already exists' in result.stderr:
        logger.info(f"Database '{db_name}' already exists")
    else:
        logger.info(f"✅ Created database '{db_name}'")

    # Grant privileges
    grant_cmd = f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};"
    subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-c', grant_cmd],
        capture_output=True,
        text=True,
        check=True
    )
    logger.info(f"✅ Granted privileges to '{db_user}'")

    return {
        'db_name': db_name,
        'db_user': db_user,
        'db_password': db_password,
        'db_host': 'localhost',
        'db_port': '5432'
    }


def update_env_file(db_config):
    """Update .env file with PostgreSQL configuration."""
    env_path = Path('.env')

    # Read existing .env
    env_lines = []
    if env_path.exists():
        with open(env_path, 'r') as f:
            env_lines = f.readlines()

    # Create backup
    if env_path.exists():
        backup_path = Path('.env.backup')
        with open(backup_path, 'w') as f:
            f.writelines(env_lines)
        logger.info(f"✅ Backed up .env to {backup_path}")

    # Update or add PostgreSQL configuration
    # URL-encode credentials to handle special characters like / + =
    encoded_user = quote_plus(db_config['db_user'])
    encoded_password = quote_plus(db_config['db_password'])

    config_vars = {
        'DB_TYPE': 'postgresql',
        'DB_HOST': db_config['db_host'],
        'DB_PORT': db_config['db_port'],
        'DB_NAME': db_config['db_name'],
        'DB_USER': db_config['db_user'],
        'DB_PASSWORD': db_config['db_password'],
        'DATABASE_URL': f"postgresql+asyncpg://{encoded_user}:{encoded_password}@{db_config['db_host']}:{db_config['db_port']}/{db_config['db_name']}",
        'SYNC_DATABASE_URL': f"postgresql+psycopg2://{encoded_user}:{encoded_password}@{db_config['db_host']}:{db_config['db_port']}/{db_config['db_name']}",
        'DB_POOL_SIZE': '20',
        'DB_MAX_OVERFLOW': '10',
        'DB_POOL_TIMEOUT': '30',
        'DB_POOL_RECYCLE': '3600'
    }

    # Track which vars we've updated
    updated_vars = set()

    # Update existing lines
    for i, line in enumerate(env_lines):
        for var, value in config_vars.items():
            if line.startswith(f"{var}="):
                env_lines[i] = f"{var}={value}\n"
                updated_vars.add(var)
                break

    # Add new variables that weren't in the file
    for var, value in config_vars.items():
        if var not in updated_vars:
            env_lines.append(f"{var}={value}\n")

    # Write updated .env
    with open(env_path, 'w') as f:
        f.writelines(env_lines)

    logger.info(f"✅ Updated {env_path} with PostgreSQL configuration")


def install_python_dependencies():
    """Install PostgreSQL Python dependencies."""
    logger.info("Installing PostgreSQL Python dependencies...")

    dependencies = [
        'asyncpg',
        'psycopg2-binary',
        'alembic',
        'sqlalchemy[asyncio]'
    ]

    for dep in dependencies:
        logger.info(f"Installing {dep}...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', dep],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            logger.error(f"Failed to install {dep}: {result.stderr}")
            return False
        logger.info(f"✅ Installed {dep}")

    return True


def configure_database_timeouts(db_config):
    """
    Configure PostgreSQL timeout safeguards to prevent connection leaks.

    CRITICAL: Sets idle_in_transaction_session_timeout to prevent the application
    from freezing due to uncommitted transactions (discovered in Week 4 testing).

    Reference: WEEK4-COMPLETION-REPORT.md - Critical Bug Fix
    """
    logger.info("Configuring database timeout safeguards...")

    # Set 60-second timeout for idle transactions
    # This prevents connection leaks from causing application freezes
    timeout_sql = f"ALTER DATABASE {db_config['db_name']} SET idle_in_transaction_session_timeout = '60s';"

    env = os.environ.copy()
    env['PGPASSWORD'] = db_config['db_password']

    result = subprocess.run(
        ['psql', '-h', db_config['db_host'], '-p', db_config['db_port'],
         '-U', db_config['db_user'], '-d', db_config['db_name'], '-c', timeout_sql],
        capture_output=True,
        text=True,
        check=False,
        env=env
    )

    if result.returncode != 0:
        logger.warning(f"⚠️  Could not set idle transaction timeout: {result.stderr}")
        logger.warning("This may lead to connection leaks under high load")
        return False

    logger.info("✅ Idle transaction timeout set to 60 seconds")
    logger.info("   This prevents connection leaks from uncommitted transactions")
    return True


def create_pgvector_extension(db_config):
    """Create pgvector extension as superuser (required for vector support)."""
    logger.info("Creating pgvector extension...")

    # Create extension as postgres superuser
    create_ext_cmd = f"CREATE EXTENSION IF NOT EXISTS vector;"
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-d', db_config['db_name'], '-c', create_ext_cmd],
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode != 0:
        if 'already exists' in result.stderr:
            logger.info("pgvector extension already exists")
            return True
        else:
            logger.error(f"Failed to create pgvector extension: {result.stderr}")
            logger.warning("⚠️  Migrations may fail without pgvector extension!")
            logger.warning("   Install with: sudo apt-get install postgresql-16-pgvector")
            return False

    logger.info("✅ pgvector extension created successfully")
    return True


def create_signal_tables(db_config):
    """Create signal_instructions and signal_alerts tables."""
    logger.info("Creating signal tables...")

    sql_script = """
-- Create signal_instructions table
CREATE TABLE IF NOT EXISTS signal_instructions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    instruction TEXT NOT NULL,
    topic TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create signal_alerts table
CREATE TABLE IF NOT EXISTS signal_alerts (
    id SERIAL PRIMARY KEY,
    article_uri TEXT NOT NULL,
    instruction_id INTEGER NOT NULL,
    instruction_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    threat_level TEXT NOT NULL,
    summary TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    FOREIGN KEY (instruction_id) REFERENCES signal_instructions(id) ON DELETE CASCADE,
    UNIQUE(article_uri, instruction_id)
);

-- Create indices for better performance
CREATE INDEX IF NOT EXISTS idx_signal_alerts_instruction_id ON signal_alerts(instruction_id);
CREATE INDEX IF NOT EXISTS idx_signal_alerts_article_uri ON signal_alerts(article_uri);
CREATE INDEX IF NOT EXISTS idx_signal_alerts_detected_at ON signal_alerts(detected_at);
CREATE INDEX IF NOT EXISTS idx_signal_alerts_is_acknowledged ON signal_alerts(is_acknowledged);
CREATE INDEX IF NOT EXISTS idx_signal_instructions_topic ON signal_instructions(topic);
CREATE INDEX IF NOT EXISTS idx_signal_instructions_is_active ON signal_instructions(is_active);
"""

    # Set environment for psql
    env = os.environ.copy()
    env['PGPASSWORD'] = db_config['db_password']

    result = subprocess.run(
        ['psql', '-h', db_config['db_host'], '-p', db_config['db_port'],
         '-U', db_config['db_user'], '-d', db_config['db_name'], '-c', sql_script],
        capture_output=True,
        text=True,
        check=False,
        env=env
    )

    if result.returncode != 0:
        logger.warning(f"Signal tables creation had warnings: {result.stderr}")
        # Don't fail - tables might already exist
        return True

    logger.info("✅ Signal tables created successfully")
    return True


def run_migrations(db_config):
    """Run Alembic migrations to create schema."""
    logger.info("Running database migrations...")

    # Set environment variables for migration
    os.environ['DB_TYPE'] = 'postgresql'
    os.environ['DB_HOST'] = db_config['db_host']
    os.environ['DB_PORT'] = db_config['db_port']
    os.environ['DB_NAME'] = db_config['db_name']
    os.environ['DB_USER'] = db_config['db_user']
    os.environ['DB_PASSWORD'] = db_config['db_password']

    # Find alembic in venv or use system alembic
    venv_alembic = Path('.venv') / 'bin' / 'alembic'
    alembic_cmd = str(venv_alembic) if venv_alembic.exists() else 'alembic'

    # Run alembic upgrade
    result = subprocess.run(
        [alembic_cmd, 'upgrade', 'head'],
        capture_output=True,
        text=True,
        check=False
    )

    if result.returncode != 0:
        logger.error(f"Migration failed: {result.stderr}")
        return False

    logger.info("✅ Database migrations completed")

    # Configure database timeouts (CRITICAL for preventing connection leaks)
    configure_database_timeouts(db_config)

    # Note: Signal tables are now created by Alembic migrations (b6a5ff4214f5)
    # No longer creating them manually to avoid conflicts

    return True


def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(description='PostgreSQL Setup for AunooAI')
    parser.add_argument('--skip-install', action='store_true', help='Skip PostgreSQL installation')
    parser.add_argument('--force', action='store_true', help='Force database recreation')
    parser.add_argument('--db-name', default='aunoo_db', help='Database name')
    parser.add_argument('--db-user', default='aunoo_user', help='Database user')
    parser.add_argument('--db-password', default=None, help='Database password (auto-generated if not provided)')

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PostgreSQL Setup for AunooAI")
    logger.info("=" * 60)

    # Step 1: Check if PostgreSQL is installed
    if not check_postgresql_installed():
        if args.skip_install:
            logger.error("PostgreSQL not found and --skip-install specified. Aborting.")
            return False

        logger.info("\n📦 PostgreSQL not found. Installing...")
        if not install_postgresql():
            logger.error("PostgreSQL installation failed. Aborting.")
            return False

    # Step 2: Install Python dependencies
    logger.info("\n📦 Installing Python dependencies...")
    if not install_python_dependencies():
        logger.error("Failed to install Python dependencies. Aborting.")
        return False

    # Step 3: Create database and user
    logger.info("\n🗄️  Setting up database...")
    db_config = create_database_and_user(
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password,
        force=args.force
    )

    if db_config is None:
        logger.error("Database setup failed. Aborting.")
        return False

    # Step 4: Update .env file
    logger.info("\n⚙️  Updating configuration...")
    update_env_file(db_config)

    # Step 5: Create pgvector extension (MUST be before migrations)
    logger.info("\n🔌 Creating pgvector extension...")
    create_pgvector_extension(db_config)

    # Step 6: Run migrations
    logger.info("\n🔄 Running database migrations...")
    if not run_migrations(db_config):
        logger.warning("⚠️  Migrations failed. You may need to run 'alembic upgrade head' manually.")

    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("✅ PostgreSQL Setup Complete!")
    logger.info("=" * 60)
    logger.info(f"\nDatabase Configuration:")
    logger.info(f"  Database: {db_config['db_name']}")
    logger.info(f"  User:     {db_config['db_user']}")
    logger.info(f"  Host:     {db_config['db_host']}")
    logger.info(f"  Port:     {db_config['db_port']}")
    logger.info(f"\n💡 Your .env file has been updated with PostgreSQL settings.")
    logger.info(f"💡 A backup was saved to .env.backup")
    logger.info(f"\n🚀 You can now start the application with: python app/run.py")

    logger.info(f"\n🔍 Database Health Monitoring:")
    logger.info(f"   Check for stuck transactions:")
    logger.info(f"   PGPASSWORD={db_config['db_password']} psql -U {db_config['db_user']} -d {db_config['db_name']} -h localhost -c \\")
    logger.info(f"     \"SELECT pid, state, NOW() - query_start AS duration FROM pg_stat_activity WHERE state = 'idle in transaction';\"")
    logger.info(f"\n⚠️  IMPORTANT: Week 4 PostgreSQL Migration Notes:")
    logger.info(f"   - Transaction timeout set to 60s to prevent connection leaks")
    logger.info(f"   - All database operations MUST call conn.commit() after queries")
    logger.info(f"   - Monitor for 'idle in transaction' connections regularly")
    logger.info(f"   - Reference: spec-files-aunoo/WEEK4-COMPLETION-REPORT.md")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
