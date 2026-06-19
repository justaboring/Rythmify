from aiohttp import web
import aiohttp_jinja2
import jinja2
from music_player import guild_states
from config import Config
from stats_store import get_stats, get_all_guild_stats
from playlist_store import get_all_playlists
from backup_restore import create_backup, list_backups, delete_backup
from recommendation_engine import (
    generate_recommendations, 
    dismiss_recommendation, 
    complete_recommendation,
    get_interaction_stats
)
from quality_store import get_quality, set_quality
import discord
import json
import os


async def handle_index(request):
    bots = request.app['bots']
    active_guilds = []
    
    for guild_id, state in guild_states.items():
        guild = None
        for b in bots:
            guild = b.get_guild(guild_id)
            if guild:
                break
        
        if guild:
            active_guilds.append({
                "id": guild_id,
                "name": guild.name,
                "current": state.current_song.title if state.current_song else "Idle",
                "current_thumbnail": state.current_song.thumbnail if state.current_song and state.current_song.thumbnail else None,
                "queue_count": len(state.queue),
                "is_active": state.current_song is not None
            })
    
    all_stats = get_all_guild_stats()
    
    # Get recommendations
    has_backups = os.path.exists("backups") and len(os.listdir("backups")) > 0 if os.path.exists("backups") else False
    playlist_count = 0
    if os.path.exists("playlists.json"):
        try:
            with open("playlists.json", "r") as f:
                playlist_data = json.load(f)
            for guild in playlist_data.values():
                for user in guild.values():
                    playlist_count += len(user)
        except:
            pass
    
    recommendations = generate_recommendations(
        guild_stats=all_stats,
        has_backups=has_backups,
        playlist_count=playlist_count,
        active_servers=len(active_guilds)
    )
    
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rythmify | Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { font-family: 'Inter', sans-serif; }
        body { 
            background: linear-gradient(135deg, #0f172a 0%, #020617 50%, #020617 100%);
            min-height: 100vh;
        }
        .glass { 
            background: rgba(255, 255, 255, 0.03); 
            backdrop-filter: blur(20px); 
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .card-hover { 
            transition: all 0.3s ease; 
        }
        .card-hover:hover { 
            transform: translateY(-4px); 
            box-shadow: 0 20px 25px -5px rgba(16, 185, 129, 0.1), 0 10px 10px -5px rgba(16, 185, 129, 0.04);
        }
        .pulse-dot {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .slide-in {
            animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
            from { transform: translateY(-10px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        .notification {
            animation: slideInRight 0.4s ease-out;
        }
        @keyframes slideInRight {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.3); }
    </style>
</head>
<body class="text-slate-100">
    <!-- Notification Container -->
    <div id="notifications" class="fixed top-4 right-4 z-50 flex flex-col gap-3"></div>

    <div class="max-w-7xl mx-auto px-4 py-8">
        <!-- Header -->
        <header class="mb-10">
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
                <div>
                    <div class="flex items-center gap-3 mb-2">
                        <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-teal-500 to-emerald-600 flex items-center justify-center shadow-xl shadow-teal-500/20">
                            <i class="fas fa-music text-xl"></i>
                        </div>
                        <h1 class="text-4xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                            Rythmify
                        </h1>
                    </div>
                    <p class="text-slate-400 text-lg">Real-time Music Bot Dashboard</p>
                </div>
                
                <div class="flex items-center gap-4">
                    <button onclick="toggleTheme()" class="glass px-4 py-2 rounded-xl hover:bg-white/10 transition flex items-center gap-2">
                        <i class="fas fa-palette"></i>
                        <span class="hidden sm:inline">Customize</span>
                    </button>
                    <div class="glass px-5 py-2 rounded-xl flex items-center gap-3">
                        <span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span>
                        <span class="text-sm font-medium text-slate-300">{{ guilds|length }} Active Servers</span>
                    </div>
                </div>
            </div>
        </header>

        {% if recommendations %}
        <!-- Recommendations Section -->
        <section class="mb-10">
            <h2 class="text-xl font-semibold text-white flex items-center gap-3 mb-6">
                <i class="fas fa-lightbulb text-yellow-400"></i>
                Rekomendasi untuk Anda
            </h2>
            <div id="recommendations-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {% for rec in recommendations %}
                <div class="recommendation-card glass card-hover rounded-3xl p-6 border border-white/10 slide-in" data-id="{{ rec.id }}">
                    <div class="flex items-start justify-between mb-4">
                        <div class="w-12 h-12 rounded-2xl bg-gradient-to-br {{ rec.color }} flex items-center justify-center shadow-lg">
                            <i class="fas {{ rec.icon }} text-xl text-white"></i>
                        </div>
                        <button onclick="dismissRecommendation('{{ rec.id }}')" class="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <h3 class="text-lg font-bold text-white mb-2">{{ rec.title }}</h3>
                    <p class="text-slate-400 text-sm mb-5">{{ rec.description }}</p>
                    {% if rec.action_text %}
                    <button onclick="completeRecommendation('{{ rec.id }}', '{{ rec.type }}')" class="w-full bg-gradient-to-r {{ rec.color }} hover:opacity-90 text-white font-semibold py-2.5 px-4 rounded-xl transition">
                        {{ rec.action_text }}
                    </button>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
        </section>
        {% endif %}

        <!-- Summary Widgets -->
        <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
            <div class="glass card-hover rounded-3xl p-6">
                <div class="flex items-start justify-between mb-4">
                    <div class="w-12 h-12 rounded-2xl bg-teal-500/20 flex items-center justify-center text-teal-400">
                        <i class="fas fa-server text-xl"></i>
                    </div>
                    <span class="text-xs font-semibold text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-full">+12%</span>
                </div>
                <h3 class="text-3xl font-bold text-white mb-1">{{ all_stats.total_guilds }}</h3>
                <p class="text-slate-400 text-sm">Total Servers</p>
            </div>

            <div class="glass card-hover rounded-3xl p-6">
                <div class="flex items-start justify-between mb-4">
                    <div class="w-12 h-12 rounded-2xl bg-purple-500/20 flex items-center justify-center text-purple-400">
                        <i class="fas fa-play-circle text-xl"></i>
                    </div>
                    <span class="text-xs font-semibold text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-full">+8%</span>
                </div>
                <h3 class="text-3xl font-bold text-white mb-1">{{ all_stats.total_plays_all }}</h3>
                <p class="text-slate-400 text-sm">Total Plays</p>
            </div>

            <div class="glass card-hover rounded-3xl p-6">
                <div class="flex items-start justify-between mb-4">
                    <div class="w-12 h-12 rounded-2xl bg-amber-500/20 flex items-center justify-center text-amber-400">
                        <i class="fas fa-fire text-xl"></i>
                    </div>
                    <span class="text-xs font-semibold text-amber-400 bg-amber-400/10 px-2 py-1 rounded-full">Active</span>
                </div>
                <h3 class="text-3xl font-bold text-white mb-1">{{ all_stats.active_guilds }}</h3>
                <p class="text-slate-400 text-sm">Active 24h</p>
            </div>

            <div class="glass card-hover rounded-3xl p-6">
                <div class="flex items-start justify-between mb-4">
                    <div class="w-12 h-12 rounded-2xl bg-rose-500/20 flex items-center justify-center text-rose-400">
                        <i class="fas fa-list-music text-xl"></i>
                    </div>
                </div>
                <h3 class="text-3xl font-bold text-white mb-1">{{ guilds|sum(attribute='queue_count') }}</h3>
                <p class="text-slate-400 text-sm">Songs in Queue</p>
            </div>
        </section>

        <!-- Search & Filter -->
        <section class="glass rounded-3xl p-6 mb-10">
            <div class="flex flex-col lg:flex-row gap-4">
                <div class="flex-1 relative">
                    <i class="fas fa-search absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"></i>
                    <input 
                        type="text" 
                        id="searchInput" 
                        placeholder="Search servers..." 
                        class="w-full bg-slate-900/50 border border-slate-700/50 rounded-2xl py-3 pl-12 pr-4 text-white placeholder-slate-400 focus:outline-none focus:border-teal-500/50 focus:ring-2 focus:ring-teal-500/20 transition"
                        oninput="filterGuilds()"
                    >
                </div>
                <select id="filterSelect" class="bg-slate-900/50 border border-slate-700/50 rounded-2xl py-3 px-4 text-white focus:outline-none focus:border-teal-500/50 focus:ring-2 focus:ring-teal-500/20 transition" onchange="filterGuilds()">
                    <option value="all">All Servers</option>
                    <option value="active">Active Only</option>
                    <option value="idle">Idle Only</option>
                </select>
            </div>
        </section>

        <!-- Guilds Grid -->
        <section class="mb-10">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-xl font-semibold text-white flex items-center gap-3">
                    <i class="fas fa-compass text-teal-400"></i>
                    Server List
                </h2>
                <button onclick="refreshData()" class="glass px-4 py-2 rounded-xl hover:bg-white/10 transition flex items-center gap-2">
                    <i class="fas fa-sync-alt" id="refreshIcon"></i>
                    <span class="hidden sm:inline">Refresh</span>
                </button>
            </div>
            
            {% if guilds %}
                <div id="guildsGrid" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {% for g in guilds %}
                        <a href="/guild/{{ g.id }}" class="glass card-hover rounded-3xl p-6 block guild-card" data-name="{{ g.name|lower }}" data-status="{{ 'active' if g.is_active else 'idle' }}">
                            <div class="flex items-start justify-between mb-5">
                                <div class="flex items-center gap-4">
                                    {% if g.current_thumbnail %}
                                        <img src="{{ g.current_thumbnail }}" alt="Thumbnail" class="w-14 h-14 rounded-2xl object-cover shadow-lg">
                                    {% else %}
                                        <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-teal-400 to-blue-600 flex items-center justify-center shadow-lg">
                                            <i class="fas fa-server text-2xl"></i>
                                        </div>
                                    {% endif %}
                                    <div>
                                        <h3 class="text-lg font-bold text-white line-clamp-1">{{ g.name }}</h3>
                                        <p class="text-sm text-slate-400">{{ g.current }}</p>
                                    </div>
                                </div>
                                <div class="flex flex-col items-end gap-2">
                                    <span class="flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full {{ 'bg-emerald-500/20 text-emerald-400' if g.is_active else 'bg-slate-500/20 text-slate-400' }}">
                                        <span class="w-1.5 h-1.5 rounded-full {{ 'bg-emerald-400' if g.is_active else 'bg-slate-400' }}"></span>
                                        {{ 'Active' if g.is_active else 'Idle' }}
                                    </span>
                                    <span class="text-xs text-slate-400 flex items-center gap-1">
                                        <i class="fas fa-music"></i>
                                        {{ g.queue_count }} songs
                                    </span>
                                </div>
                            </div>
                            <div class="flex items-center gap-2 text-sm text-slate-400">
                                <i class="fas fa-arrow-right text-teal-400"></i>
                                <span>Click for details</span>
                            </div>
                        </a>
                    {% endfor %}
                </div>
            {% else %}
                <div class="glass rounded-3xl p-16 text-center">
                    <i class="fas fa-inbox text-6xl text-slate-600 mb-4"></i>
                    <h3 class="text-xl font-semibold text-slate-300 mb-2">No active servers</h3>
                    <p class="text-slate-500">Start playing music on a server to see it here</p>
                </div>
            {% endif %}
        </section>

        <!-- Global Activity Chart -->
        <section class="glass rounded-3xl p-6 mb-8">
            <h2 class="text-xl font-semibold text-white flex items-center gap-3 mb-6">
                <i class="fas fa-chart-line text-purple-400"></i>
                Global Activity
            </h2>
            <div class="h-80">
                <canvas id="globalChart"></canvas>
            </div>
        </section>

        <!-- Backup Management -->
        <section class="glass rounded-3xl p-6 mb-8">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-xl font-semibold text-white flex items-center gap-3">
                    <i class="fas fa-box-archive text-amber-400"></i>
                    Backup Management
                </h2>
                <button onclick="createBackup()" class="bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 px-6 py-2 rounded-xl font-semibold transition flex items-center gap-2">
                    <i class="fas fa-plus"></i>
                    Create Backup
                </button>
            </div>
            <div id="backupList" class="space-y-3">
                <p class="text-slate-400 text-center py-8">Loading backups...</p>
            </div>
        </section>
    </div>

    <script>
        // Notification system
        function showNotification(message, type = 'info') {
            const container = document.getElementById('notifications');
            const colors = {
                info: 'bg-blue-500',
                success: 'bg-emerald-500',
                warning: 'bg-amber-500',
                error: 'bg-rose-500'
            };
            const icons = {
                info: 'fa-info-circle',
                success: 'fa-check-circle',
                warning: 'fa-exclamation-circle',
                error: 'fa-times-circle'
            };
            
            const div = document.createElement('div');
            div.className = `notification glass ${colors[type]} text-white px-6 py-4 rounded-2xl shadow-xl flex items-center gap-4 max-w-sm`;
            div.innerHTML = `
                <i class="fas ${icons[type]} text-xl"></i>
                <span class="flex-1">${message}</span>
                <button onclick="this.parentElement.remove()" class="hover:opacity-70">
                    <i class="fas fa-times"></i>
                </button>
            `;
            container.appendChild(div);
            
            setTimeout(() => div.remove(), 5000);
        }

        // Filter guilds
        function filterGuilds() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const filterStatus = document.getElementById('filterSelect').value;
            const cards = document.querySelectorAll('.guild-card');
            
            cards.forEach(card => {
                const name = card.dataset.name;
                const status = card.dataset.status;
                const matchesSearch = name.includes(searchTerm);
                const matchesFilter = filterStatus === 'all' || filterStatus === status;
                
                if (matchesSearch && matchesFilter) {
                    card.classList.remove('hidden');
                    card.classList.add('slide-in');
                } else {
                    card.classList.add('hidden');
                }
            });
        }

        // Refresh data
        function refreshData() {
            const icon = document.getElementById('refreshIcon');
            icon.classList.add('animate-spin');
            setTimeout(() => {
                location.reload();
            }, 500);
        }

        // Theme customization
        let isDark = true;
        function toggleTheme() {
            isDark = !isDark;
            showNotification(isDark ? 'Dark mode enabled' : 'Light mode enabled (simulation)', 'success');
        }

        // Global chart
        document.addEventListener('DOMContentLoaded', function() {
            const ctx = document.getElementById('globalChart');
            if (ctx) {
                const hourlyData = Array.from({length: 24}, () => Math.floor(Math.random() * 20));
                const labels = Array.from({length: 24}, (_, i) => `${i}:00`);
                
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Music Plays',
                            data: hourlyData,
                            borderColor: '#14b8a6',
                            backgroundColor: 'rgba(20, 184, 166, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointBackgroundColor: '#14b8a6',
                            pointBorderColor: '#0f172a',
                            pointBorderWidth: 2,
                            pointRadius: 4,
                            pointHoverRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            },
                            y: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            }
                        }
                    }
                });
            }

            // Auto refresh every 30 seconds
            setTimeout(() => location.reload(), 30000);
            
            // Load backups on page load
            loadBackups();
        });

        // Backup management functions
        async function loadBackups() {
            try {
                const response = await fetch('/api/backup/list');
                const data = await response.json();
                
                if (data.success) {
                    renderBackups(data.backups);
                } else {
                    showNotification('Failed to load backups', 'error');
                }
            } catch (e) {
                showNotification('Error loading backups', 'error');
            }
        }

        function renderBackups(backups) {
            const container = document.getElementById('backupList');
            
            if (backups.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <i class="fas fa-inbox text-4xl text-slate-600 mb-3"></i>
                        <p class="text-slate-400">No backups yet</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = backups.map(b => `
                <div class="glass rounded-2xl p-4 flex items-center justify-between">
                    <div class="flex items-center gap-4">
                        <div class="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center text-amber-400">
                            <i class="fas fa-file-archive"></i>
                        </div>
                        <div>
                            <h4 class="font-semibold text-white">${b.name}</h4>
                            <p class="text-sm text-slate-400">${(b.size / 1024 / 1024).toFixed(2)} MB • ${new Date(b.created * 1000).toLocaleString()}</p>
                        </div>
                    </div>
                    <button onclick="deleteBackup('${b.name}')" class="text-rose-400 hover:text-rose-300 p-2 rounded-xl hover:bg-rose-500/10 transition">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `).join('');
        }

        async function createBackup() {
            try {
                showNotification('Creating backup...', 'info');
                const response = await fetch('/api/backup/create', {
                    method: 'POST'
                });
                const data = await response.json();
                
                if (data.success) {
                    showNotification('Backup created successfully!', 'success');
                    loadBackups();
                } else {
                    showNotification('Failed to create backup', 'error');
                }
            } catch (e) {
                showNotification('Error creating backup', 'error');
            }
        }

        async function deleteBackup(name) {
            if (!confirm('Are you sure you want to delete this backup?')) return;
            
            try {
                const response = await fetch('/api/backup/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name })
                });
                const data = await response.json();
                
                if (data.success) {
                    showNotification('Backup deleted!', 'success');
                    loadBackups();
                } else {
                    showNotification('Failed to delete backup', 'error');
                }
            } catch (e) {
                showNotification('Error deleting backup', 'error');
            }
        }

        // Recommendation functions
        async function dismissRecommendation(id) {
            const card = document.querySelector(`.recommendation-card[data-id="${id}"]`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                card.style.transition = 'all 0.3s ease';
                setTimeout(() => card.remove(), 300);
            }
            
            try {
                await fetch('/api/recommendations/dismiss', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: id })
                });
                showNotification('Rekomendasi disembunyikan', 'info');
            } catch (e) {
                console.error('Error dismissing recommendation:', e);
            }
        }

        async function completeRecommendation(id, type) {
            const card = document.querySelector(`.recommendation-card[data-id="${id}"]`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                card.style.transition = 'all 0.3s ease';
                setTimeout(() => card.remove(), 300);
            }
            
            try {
                await fetch('/api/recommendations/complete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: id })
                });
                
                // Handle specific actions
                if (type === 'warning' && id === 'backup_reminder') {
                    await createBackup();
                }
                
                showNotification('Rekomendasi selesai! ✨', 'success');
            } catch (e) {
                console.error('Error completing recommendation:', e);
            }
        }
    </script>
</body>
</html>
    """
    temp = jinja2.Template(html)
    return web.Response(text=temp.render(guilds=active_guilds, all_stats=all_stats, recommendations=recommendations), content_type='text/html')


async def handle_action(request):
    bots = request.app['bots']
    data = await request.json()
    guild_id = int(data.get('guild_id'))
    action = data.get('action')
    
    guild = None
    for b in bots:
        guild = b.get_guild(guild_id)
        if guild:
            break
    
    state = guild_states.get(guild_id)
    
    if not guild or not state or not guild.voice_client:
        return web.json_response({"success": False, "error": "Not connected"})

    if action == "pause":
        if guild.voice_client.is_playing():
            guild.voice_client.pause()
            state.is_paused = True
        elif guild.voice_client.is_paused():
            guild.voice_client.resume()
            state.is_paused = False
    elif action == "skip":
        guild.voice_client.stop()
    elif action == "stop":
        state.clear()
        guild.voice_client.stop()
        
    return web.json_response({"success": True})


async def handle_guild(request):
    bots = request.app['bots']
    guild_id = int(request.match_info['id'])
    state = guild_states.get(guild_id)
    
    guild = None
    for b in bots:
        guild = b.get_guild(guild_id)
        if guild:
            break
    
    stats = get_stats(guild_id)
    if not guild:
        return web.Response(text="Guild not found or inactive", status=404)
    
    current_quality = get_quality(guild_id)
    quality_preset = Config.VOICE_QUALITY_PRESETS.get(current_quality, Config.VOICE_QUALITY_PRESETS[Config.DEFAULT_QUALITY])
    
    queue_list = [{"title": s.title, "duration": s.format_duration() if hasattr(s, 'format_duration') and s.duration else "?:??"} for s in state.queue[:20]]
    
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ name }} | Rythmify</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * { font-family: 'Inter', sans-serif; }
        body { 
            background: linear-gradient(135deg, #0f172a 0%, #020617 50%, #020617 100%);
            min-height: 100vh;
        }
        .glass { 
            background: rgba(255, 255, 255, 0.03); 
            backdrop-filter: blur(20px); 
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .btn-action { 
            transition: all 0.2s; 
        }
        .btn-action:hover { 
            transform: scale(1.05); 
            filter: brightness(1.1); 
        }
        .btn-action:active { 
            transform: scale(0.95); 
        }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 4px; }
        .quality-btn.active {
            border-color: #06b6d4;
            box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.2);
        }
    </style>
</head>
<body class="text-slate-100">
    <div class="max-w-7xl mx-auto px-4 py-8">
        <!-- Back Button -->
        <div class="mb-8">
            <a href="/" class="inline-flex items-center gap-3 text-slate-400 hover:text-teal-400 transition group">
                <i class="fas fa-chevron-left group-hover:-translate-x-1 transition"></i>
                <span class="text-lg font-medium">Back to Dashboard</span>
            </a>
        </div>

        <!-- Now Playing Section -->
        <section class="glass rounded-3xl p-8 mb-8 relative overflow-hidden">
            <div class="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-teal-500/20 to-transparent rounded-full blur-3xl"></div>
            <div class="relative z-10">
                <div class="flex flex-col lg:flex-row gap-10">
                    <!-- Album Art & Info -->
                    <div class="lg:w-1/3">
                        {% if state.current_song and state.current_song.thumbnail %}
                            <img src="{{ state.current_song.thumbnail }}" alt="Album Art" class="w-full aspect-square rounded-3xl object-cover shadow-2xl">
                        {% else %}
                            <div class="w-full aspect-square rounded-3xl bg-gradient-to-br from-teal-500/30 to-purple-500/30 flex items-center justify-center shadow-2xl">
                                <i class="fas fa-music text-8xl text-white/50"></i>
                            </div>
                        {% endif %}
                    </div>
                    
                    <!-- Controls & Details -->
                    <div class="lg:w-2/3 flex flex-col justify-between">
                        <div>
                            <span class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-teal-500/20 text-teal-400 text-xs font-semibold uppercase tracking-wider mb-4">
                                <span class="w-2 h-2 rounded-full bg-teal-400 animate-pulse"></span>
                                {{ 'Now Playing' if state.current_song else 'Idle' }}
                            </span>
                            <h1 class="text-4xl lg:text-5xl font-black text-white mb-3 line-clamp-2">
                                {{ state.current_song.title if state.current_song else 'No song playing' }}
                            </h1>
                            <p class="text-xl text-slate-400 font-light mb-2">
                                <i class="fas fa-server mr-2"></i>{{ name }}
                            </p>
                            <p class="text-slate-500 text-lg mb-8">
                                Total plays: <span class="text-teal-400 font-semibold">{{ stats.total_played }}</span> songs
                            </p>
                        </div>
                        
                        <!-- Control Buttons -->
                        <div class="flex items-center gap-4">
                            <button onclick="sendAction('pause')" class="btn-action w-16 h-16 rounded-2xl bg-white text-slate-900 flex items-center justify-center text-2xl shadow-xl shadow-white/10">
                                <i class="fas fa-play-pause"></i>
                            </button>
                            <button onclick="sendAction('skip')" class="btn-action w-16 h-16 rounded-2xl glass flex items-center justify-center text-2xl border border-white/10">
                                <i class="fas fa-forward-step text-white"></i>
                            </button>
                            <button onclick="sendAction('stop')" class="btn-action w-16 h-16 rounded-2xl bg-rose-500/20 text-rose-400 flex items-center justify-center text-2xl border border-rose-500/30">
                                <i class="fas fa-stop"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Quality Settings -->
        <section class="glass rounded-3xl p-6 mb-8">
            <h2 class="text-lg font-semibold text-white mb-6 flex items-center gap-3">
                <i class="fas fa-sliders text-cyan-400"></i>
                Audio Quality
            </h2>
            <div class="mb-6">
                <div class="flex items-center gap-4 mb-4">
                    <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center">
                        <i class="fas fa-music text-2xl"></i>
                    </div>
                    <div>
                        <h3 class="text-xl font-bold text-white" id="currentQualityName">{{ current_quality_preset.description }}</h3>
                        <p class="text-slate-400 text-sm">
                            Bitrate: <span class="text-cyan-400 font-semibold" id="currentBitrate">{{ current_quality_preset.bitrate }}</span>
                            | Buffer: <span class="text-cyan-400 font-semibold" id="currentBuffer">{{ current_quality_preset.buffersize }}</span>
                        </p>
                    </div>
                </div>
            </div>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <button onclick="setQuality('low')" class="quality-btn glass rounded-2xl p-4 border border-white/10 hover:border-red-500/30 transition text-center" id="quality-low">
                    <i class="fas fa-signal text-2xl text-red-400 mb-2"></i>
                    <h4 class="font-bold text-white">Low</h4>
                    <p class="text-xs text-slate-400">48kbps</p>
                </button>
                <button onclick="setQuality('medium')" class="quality-btn glass rounded-2xl p-4 border border-white/10 hover:border-amber-500/30 transition text-center" id="quality-medium">
                    <i class="fas fa-signal text-2xl text-amber-400 mb-2"></i>
                    <h4 class="font-bold text-white">Medium</h4>
                    <p class="text-xs text-slate-400">128kbps</p>
                </button>
                <button onclick="setQuality('high')" class="quality-btn glass rounded-2xl p-4 border border-white/10 hover:border-emerald-500/30 transition text-center" id="quality-high">
                    <i class="fas fa-signal text-2xl text-emerald-400 mb-2"></i>
                    <h4 class="font-bold text-white">High</h4>
                    <p class="text-xs text-slate-400">256kbps</p>
                </button>
                <button onclick="setQuality('lossless')" class="quality-btn glass rounded-2xl p-4 border border-white/10 hover:border-blue-500/30 transition text-center" id="quality-lossless">
                    <i class="fas fa-crown text-2xl text-blue-400 mb-2"></i>
                    <h4 class="font-bold text-white">Lossless</h4>
                    <p class="text-xs text-slate-400">Best</p>
                </button>
            </div>
            <p class="text-slate-500 text-sm mt-4 text-center">
                <i class="fas fa-info-circle mr-1"></i>
                Changes apply to next song
            </p>
        </section>

        <!-- Stats Grid -->
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
            <!-- Queue -->
            <div class="glass rounded-3xl p-6">
                <h2 class="text-lg font-semibold text-white mb-6 flex items-center gap-3">
                    <i class="fas fa-list-ul text-purple-400"></i>
                    Queue ({{ queue|length }})
                </h2>
                <div class="space-y-3 max-h-96 overflow-y-auto">
                    {% for item in queue %}
                        <div class="glass rounded-xl p-4 border border-white/5 hover:bg-white/10 transition">
                            <div class="flex items-center gap-3">
                                <span class="text-slate-500 font-mono text-sm w-6">{{ loop.index }}</span>
                                <div class="flex-1 min-w-0">
                                    <p class="text-white text-sm truncate">{{ item.title }}</p>
                                    <p class="text-slate-500 text-xs">{{ item.duration }}</p>
                                </div>
                            </div>
                        </div>
                    {% else %}
                        <div class="text-center py-12 text-slate-500">
                            <i class="fas fa-inbox text-3xl mb-3 opacity-50"></i>
                            <p>Queue is empty</p>
                        </div>
                    {% endfor %}
                </div>
            </div>

            <!-- Top Songs -->
            <div class="glass rounded-3xl p-6">
                <h2 class="text-lg font-semibold text-white mb-6 flex items-center gap-3">
                    <i class="fas fa-crown text-amber-400"></i>
                    Top Songs
                </h2>
                <div class="space-y-3">
                    {% for title, count in stats.top_songs %}
                        <div class="glass rounded-xl p-4 border border-white/5 hover:bg-white/10 transition">
                            <div class="flex items-center justify-between mb-2">
                                <span class="text-xs font-mono text-slate-500">#{{ loop.index }}</span>
                                <span class="bg-teal-500/20 text-teal-400 text-[10px] font-bold px-2 py-0.5 rounded-full">{{ count }}x</span>
                            </div>
                            <p class="text-sm text-slate-200 line-clamp-2">{{ title }}</p>
                        </div>
                    {% else %}
                        <div class="text-center py-12 text-slate-500">
                            <i class="fas fa-chart-bar text-3xl mb-3 opacity-50"></i>
                            <p>No data yet</p>
                        </div>
                    {% endfor %}
                </div>
            </div>

            <!-- Top Artists -->
            <div class="glass rounded-3xl p-6">
                <h2 class="text-lg font-semibold text-white mb-6 flex items-center gap-3">
                    <i class="fas fa-user-music text-pink-400"></i>
                    Top Artists
                </h2>
                <div class="space-y-3">
                    {% for artist, count in stats.top_artists %}
                        <div class="glass rounded-xl p-4 border border-white/5 hover:bg-white/10 transition">
                            <div class="flex items-center justify-between mb-2">
                                <span class="text-xs font-mono text-slate-500">#{{ loop.index }}</span>
                                <span class="bg-pink-500/20 text-pink-400 text-[10px] font-bold px-2 py-0.5 rounded-full">{{ count }}x</span>
                            </div>
                            <p class="text-sm text-slate-200">{{ artist }}</p>
                        </div>
                    {% else %}
                        <div class="text-center py-12 text-slate-500">
                            <i class="fas fa-users text-3xl mb-3 opacity-50"></i>
                            <p>No data yet</p>
                        </div>
                    {% endfor %}
                </div>
            </div>
        </section>

        <!-- Charts Section -->
        <section class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- Hourly Chart -->
            <div class="glass rounded-3xl p-6">
                <h2 class="text-lg font-semibold text-white mb-6 flex items-center gap-3">
                    <i class="fas fa-clock text-cyan-400"></i>
                    Hourly Activity
                </h2>
                <div class="h-64">
                    <canvas id="hourlyChart"></canvas>
                </div>
            </div>

            <!-- Daily Chart -->
            <div class="glass rounded-3xl p-6">
                <h2 class="text-lg font-semibold text-white mb-6 flex items-center gap-3">
                    <i class="fas fa-calendar text-indigo-400"></i>
                    Daily Activity
                </h2>
                <div class="h-64">
                    <canvas id="dailyChart"></canvas>
                </div>
            </div>
        </section>
    </div>

    <!-- Loading Overlay -->
    <div id="loading-overlay" class="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 hidden">
        <div class="glass rounded-3xl p-8 flex flex-col items-center gap-4">
            <i class="fas fa-spinner fa-spin text-4xl text-teal-400"></i>
            <p class="text-white text-lg">Processing...</p>
        </div>
    </div>

    <script>
        const stats = {{ stats|tojson }};
        
        function sendAction(action) {
            document.getElementById('loading-overlay').classList.remove('hidden');
            fetch('/api/action', { 
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({guild_id: {{ guild_id }}, action: action})
            }).then(() => {
                setTimeout(() => location.reload(), 500);
            }).catch(error => {
                console.error('Error:', error);
                document.getElementById('loading-overlay').classList.add('hidden');
                alert('Action failed');
            });
        }

        async function setQuality(quality) {
            try {
                const response = await fetch('/api/quality', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        guild_id: {{ guild_id }},
                        quality: quality
                    })
                });
                const data = await response.json();
                if (data.success) {
                    // Update UI
                    updateQualityUI(quality, data.preset);
                    showNotification('Quality updated!', 'success');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Failed to update quality');
            }
        }

        function updateQualityUI(quality, preset) {
            // Remove active from all
            document.querySelectorAll('.quality-btn').forEach(btn => btn.classList.remove('active'));
            // Add active to selected
            const activeBtn = document.getElementById('quality-' + quality);
            if (activeBtn) activeBtn.classList.add('active');
            // Update labels
            document.getElementById('currentQualityName').textContent = preset.description;
            document.getElementById('currentBitrate').textContent = preset.bitrate;
            document.getElementById('currentBuffer').textContent = preset.buffersize;
        }

        function showNotification(message, type) {
            // Simple notification
            const notif = document.createElement('div');
            notif.className = `fixed top-4 right-4 px-6 py-3 rounded-2xl glass text-white z-50`;
            notif.style.background = type === 'success' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)';
            notif.style.border = '1px solid rgba(255,255,255,0.1)';
            notif.innerHTML = `<i class="fas fa-check mr-2"></i>${message}`;
            document.body.appendChild(notif);
            setTimeout(() => {
                notif.style.transition = 'opacity 0.3s';
                notif.style.opacity = '0';
                setTimeout(() => notif.remove(), 300);
            }, 2500);
        }

        document.addEventListener('DOMContentLoaded', function() {
            // Initialize active quality
            updateQualityUI('{{ current_quality }}', {{ current_quality_preset|tojson }});
            
            // Hourly Chart
            const hourlyCtx = document.getElementById('hourlyChart');
            if (hourlyCtx) {
                const hourlyLabels = stats.hourly_stats.map(d => d.hour + ':00');
                const hourlyCounts = stats.hourly_stats.map(d => d.count);
                
                new Chart(hourlyCtx, {
                    type: 'bar',
                    data: {
                        labels: hourlyLabels,
                        datasets: [{
                            label: 'Plays',
                            data: hourlyCounts,
                            backgroundColor: 'rgba(34, 211, 238, 0.3)',
                            borderColor: '#22d3ee',
                            borderWidth: 1,
                            borderRadius: 8
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            },
                            y: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            }
                        }
                    }
                });
            }

            // Daily Chart
            const dailyCtx = document.getElementById('dailyChart');
            if (dailyCtx) {
                const dailyLabels = stats.daily_stats.map(d => d.day);
                const dailyCounts = stats.daily_stats.map(d => d.count);
                
                new Chart(dailyCtx, {
                    type: 'line',
                    data: {
                        labels: dailyLabels,
                        datasets: [{
                            label: 'Plays',
                            data: dailyCounts,
                            borderColor: '#818cf8',
                            backgroundColor: 'rgba(129, 140, 248, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointBackgroundColor: '#818cf8',
                            pointBorderColor: '#0f172a',
                            pointBorderWidth: 2,
                            pointRadius: 4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            },
                            y: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: 'rgba(255,255,255,0.5)' }
                            }
                        }
                    }
                });
            }
        });
    </script>
</body>
</html>
    """
    temp = jinja2.Template(html)
    return web.Response(text=temp.render(
        name=guild.name, 
        guild_id=guild_id,
        state=state,
        queue=queue_list,
        stats=stats,
        current_quality=current_quality,
        current_quality_preset=quality_preset
    ), content_type='text/html')


async def handle_backup_create(request):
    """Create a backup"""
    try:
        backup_path = create_backup()
        return web.json_response({"success": True, "path": backup_path})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_backup_list(request):
    """List all backups"""
    try:
        backups = list_backups()
        # Format for frontend
        formatted = []
        for b in backups:
            formatted.append({
                "name": b["name"],
                "size": b["size"],
                "created": b["created"]
            })
        return web.json_response({"success": True, "backups": formatted})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_backup_delete(request):
    """Delete a backup"""
    try:
        data = await request.json()
        backup_name = data.get('name')
        if delete_backup(backup_name):
            return web.json_response({"success": True})
        else:
            return web.json_response({"success": False, "error": "Backup not found"})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_recommendation_dismiss(request):
    """Dismiss a recommendation"""
    try:
        data = await request.json()
        rec_id = data.get('id')
        dismiss_recommendation(rec_id)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})

async def handle_recommendation_complete(request):
    """Mark a recommendation as completed"""
    try:
        data = await request.json()
        rec_id = data.get("id")
        complete_recommendation(rec_id)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


async def handle_quality_get(request):
    """Get current quality for a guild"""
    try:
        guild_id = int(request.query.get("guild_id"))
        current_quality = get_quality(guild_id)
        preset = Config.VOICE_QUALITY_PRESETS.get(current_quality)
        return web.json_response({
            "success": True,
            "current": current_quality,
            "preset": preset
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


async def handle_quality_set(request):
    """Set quality for a guild"""
    try:
        data = await request.json()
        guild_id = int(data.get("guild_id"))
        quality = data.get("quality")
        # Since dashboard is owner-only, we use dummy values
        changed = set_quality(guild_id, "Web Dashboard", quality, 0, "Web User")
        preset = Config.VOICE_QUALITY_PRESETS.get(quality)
        return web.json_response({
            "success": True,
            "changed": changed,
            "preset": preset
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})


async def start_dashboard(bots):
    app = web.Application()
    app['bots'] = bots
    app.router.add_get('/', handle_index)
    app.router.add_get('/guild/{id}', handle_guild)
    app.router.add_post('/api/action', handle_action)
    app.router.add_post('/api/backup/create', handle_backup_create)
    app.router.add_get('/api/backup/list', handle_backup_list)
    app.router.add_post('/api/backup/delete', handle_backup_delete)
    app.router.add_post('/api/recommendations/dismiss', handle_recommendation_dismiss)
    app.router.add_post('/api/recommendations/complete', handle_recommendation_complete)
    app.router.add_get('/api/quality', handle_quality_get)
    app.router.add_post('/api/quality', handle_quality_set)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.DASHBOARD_PORT)
    print(f"[Web] Dashboard running at http://localhost:{Config.DASHBOARD_PORT}")
    await site.start()
