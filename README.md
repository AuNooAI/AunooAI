# Install

## Requirements

AuNoo AI requires Python 3.11.

## Setup: Local Development, bare metal

For local development, on your host machine, ```tox``` is required.

1. Create a python virtual environment, activate and install tox:

```bash
python -m venv venv
source venv/bin/activate
pip install tox
```

2. Configure

Copy ```.env.sample``` to ```.env``` and configure:

TODO: Add config documentation.

3. Set a temporary ```admin``` password:

NOTE: This command will store the password in your shell's history. Use a temporary password. You will be prompted to 
reset the password upon first login, via the User Interface.

```bash
tox -e reset-admin-password -- --password default_password
```

4. Refresh the vector database:

```bash
tox -e reindex-chromadb
```

5. Start server:

```bash
tox -e run-dev
```

6. Login:

http://localhost:10000/

TODO: Document configured port at step 2.