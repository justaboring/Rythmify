# Dashboard Recommendation Feature

## Description
The recommendation feature provides personalized suggestions to dashboard users based on:
- Time of day (morning/afternoon/evening/night)
- Feature usage status (backup, playlist)
- Interaction history

## File Structure
```
discord-music-bot/
├── recommendation_engine.py      # Main recommendation engine
├── recommendations.json          # Recommendation status storage
├── recommendation_interactions.json  # User interaction logs
└── docs/
    └── RECOMMENDATIONS.md        # This documentation
```

## Recommendation Types

### 1. Mood Recommendations (Time-based)
- **Morning Vibes** (06:00 - 12:00): Calm morning songs
- **Afternoon Energy** (12:00 - 17:00): Upbeat productivity songs
- **Evening Chill** (17:00 - 22:00): Relaxing evening/night music
- **Night Relax** (22:00 - 06:00): Soft songs for night time

### 2. Backup Recommendations
- Shown if no backups exist
- High priority

### 3. Playlist Recommendations
- Shown if user has no playlists
- Informs about playlist feature

### 4. Feature Recommendations
- Audio filters
- Lyrics feature
- Control panel

### 5. Inspiration
- Tips for playing music together
- Tips for exploring new genres

## API Endpoints

### `POST /api/recommendations/dismiss`
Mark a recommendation as dismissed and don't show it again

**Body:**
```json
{
  "id": "mood_recommendation"
}
```

### `POST /api/recommendations/complete`
Mark a recommendation as completed

**Body:**
```json
{
  "id": "backup_reminder"
}
```

## How to Add New Recommendations

1. Edit `recommendation_engine.py`
2. Add conditions in the `generate_recommendations()` function
3. Make sure to give each recommendation a unique ID
4. Set priority (1 = highest)

Example:
```python
recommendations.append({
    "id": "new_feature_tip",
    "type": "tip",
    "title": "New Feature",
    "description": "Feature description",
    "icon": "fa-star",
    "color": "from-blue-500 to-indigo-500",
    "action_text": "Try Now",
    "priority": 3
})
```

## Logging
All user interactions with recommendations are logged in `recommendation_interactions.json` for analytics.

## Reset Recommendations
For testing, use the `reset_recommendations()` function from `recommendation_engine.py`
