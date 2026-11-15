Shielded Labs Workstation
=========================

A private board for your own work: open items, decisions, notes, links,
dates, and a page for each project or group you care about.

It lives on your Mac only. There is no account and no server, and it
starts empty, with only the public Shielded Labs projects and their links
set up: you fill it your way.

Install
-------
1. Drag "Shielded Labs.app" to your Applications folder and open it.
2. macOS will refuse the first time, because the app is not from the
   App Store. Open System Settings > Privacy & Security, scroll down to
   the line about "Shielded Labs" and click "Open Anyway".
   On older versions of macOS: right-click the app, choose Open, then
   Open again.
3. Type your name on the welcome page.

What leaves your Mac
--------------------
Nothing, unless you connect something yourself. Three things are optional
and off until you turn them on:

- AI assistant: the text you paste, or your question together with what
  is in the app, goes to the AI service you chose. A model running on
  your own Mac keeps everything local.
- Calendar: the app downloads your calendar from the private address
  you paste.
- GitHub: the app reads the open pull requests and issues of the
  repositories you list.

Your API key, GitHub token and calendar address are kept in the macOS
Keychain, never in a file. macOS may ask for your password the first
time the app reads them; choose "Always Allow".

Where your data is
------------------
~/Library/Application Support/Shielded Labs Workstation

To back up or move your board, copy that folder. To start over, delete it.
A new version of the app never touches that folder.
To see if there is one: menu Shielded Labs > Check for Updates. The app
only asks when you click, and sends nothing about you.

Requirements: macOS 13 or later, on Apple silicon or Intel.
