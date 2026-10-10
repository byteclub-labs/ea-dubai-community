# ea-dubai-community
A community page for enterprise architects in Dubai to share their views on how AI is changing the EA landscape — register, leave a short testimony, share your point of view.

## Run locally

Requires Python 3 (standard library only — nothing to install):

```
python3 server.py
```

Then open http://localhost:8000. Set `PORT` to change the port.

Registrations and testimonies persist in `data/community.db` (SQLite, auto-created on first run and gitignored).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/testimonies` | `{count, testimonies[]}` newest first |
| POST | `/api/members` | Register `{name, email, title?, organization?}` |
| POST | `/api/testimonies` | Publish/update a view `{email, text}` (≤500 chars) |
