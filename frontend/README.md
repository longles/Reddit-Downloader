# Reddit Archiver

## Overview
The Reddit Archiver is a web application that allows users to archive posts from Reddit. It provides a user-friendly dashboard for inputting usernames, managing download options, and monitoring the status of archiving jobs.

## Project Structure
```
reddit-archiver
├── public
│   ├── css
│   │   └── styles.css        # Contains the CSS styles for the application
│   ├── js
│   │   ├── app.js            # Main JavaScript logic for user interactions and state management
│   │   └── socket-handlers.js # Socket.IO event handlers for real-time updates
│   └── index.html            # HTML structure for the Reddit Archiver Dashboard
├── package.json               # npm configuration file with dependencies and scripts
├── server.js                  # Entry point for the server-side application
└── README.md                  # Documentation for the project
```

## Setup Instructions
1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd reddit-archiver
   ```

2. **Install dependencies:**
   ```
   npm install
   ```

3. **Run the server:**
   ```
   node server.js
   ```

4. **Access the application:**
   Open your web browser and navigate to `http://localhost:3000`.

## Usage Guidelines
- Enter a Reddit username in the input field to start archiving posts.
- Set the download limit and the number of concurrent downloads as needed.
- Monitor the job status and logs in the dashboard.

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.