# Handover checklist: Church Announcer

- [ ] `docs/media-team-guide.pdf` added to the repo (it's already made, so don't regenerate it).
- [ ] Page 3 of the guide: repo address filled in.
- [ ] Page 4 of the guide: contacts filled in.
- [ ] Each media team member's GitHub account added as a collaborator with **Write** access (Settings → Collaborators → Add people → role *Write*). They need this to press **Run workflow**. Each person must accept the email invitation.
- [ ] Baseline captured in [case-study-baseline.md](case-study-baseline.md).
- [ ] Full test run done together with the media team before the first Sunday:
  1. The secretary posts a realistic set of announcements in the group, including a name, a date, a time and a ₦ amount.
  2. A media team member presses **Actions → Church Announcer → Run workflow**.
  3. The script and MP3 arrive in the group.
  4. The media team plays the MP3 on the church sound system and checks every name, date, time and amount against the message.
  5. Someone sends `/preview` with a short text and confirms that only a script comes back.
  6. Someone sends a short "Thanks" in the group and confirms the bot stays quiet.
  7. Everyone agrees on the Sunday routine: the script goes in by 07:00, and the MP3 is ready by 07:15.
