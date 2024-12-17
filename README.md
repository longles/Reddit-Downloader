# Reddit Archiver

Reddit Archiver is a tool to download and archive Reddit user submissions. It supports downloading images, videos, and galleries, and removes duplicate files.

## Features

- Download images, videos, and galleries from Reddit user submissions
- Remove duplicate files
- Configurable download limits and concurrency

## Installation

1. Clone the repository:
    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

3. Create a `reddit.env` file with your Reddit API credentials:
    ```env
    client_id=your_client_id
    client_secret=your_client_secret
    username=your_username
    password=your_password
    ```

## Usage

Run the archiver from the command line:
```python
python main.py <reddit-username> [-l <submission-limit>] [-c <concurrent-downloads>]
```