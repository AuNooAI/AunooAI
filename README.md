# AuNoo AI

## Overview

An app that allows you to research and analyze news articles and trends. It uses LLMs and ML to extract insights from articles.

## Getting Started

### Run the application:

#### Create the virtual python environment
```
python -m venv .venv
```

#### Load the virtual python environment
```
source .venv/bin/activate
```

#### Install dependencies
```
pip install -r requirements.txt
```

#### Start the app
```
python app/run.py
```

#### Launch the app
https://localhost:8000

### Docker container

To build the container:
```
docker build -t newsaddict .
```

To run the container:
```
docker compose up <instance_name>
```

The docker compose file contains example instances called `newsaddict-test` and `newsaddict-customer-x`, and `newsaddict-customer-y`.

To run the container with the default instance (`newsaddict-test`):
```
docker compose up
```

To run the customer-x instance (`newsaddict-customer-x`):
``` 
docker compose --profile customer-x up
```
