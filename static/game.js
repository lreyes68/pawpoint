//Maps: Lmk which ones you like the best
// https://tile.openstreetmap.org/{z}/{x}/{y}.png
// https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png
// https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png

var map
var currentMarker
var userSelection = null
var submitted      = false
var pollTimer            = null
var countdownTimer       = null
var interludeTimer       = null
var observerTimer        = null
var currentRoundId       = null
var localSecondsLeft     = 0
var interludeSecondsLeft = 0
var observerSecondsLeft  = 0
var wasWaiting           = true
var targetMarker         = null
var targetLine           = null
var eliminatedShown      = false
var lastLoadedImage      = false

// ---- helpers ----------------------------------------------------------------

function apiFetch(url, method, body) {
    var opts = {
        method: method || 'GET',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' }
    }
    if (body) opts.body = JSON.stringify(body)
    return fetch(url, opts).then(function(r) { return r.json() })
}

function updateHPBar(hp) {
    var bar = document.getElementById('hp-bar')
    var label = document.getElementById('hp-label')
    if (!bar) return
    var pct = Math.max(0, Math.min(100, (hp / 6000) * 100))
    bar.style.width = pct + '%'
    bar.style.backgroundColor = pct > 50 ? '#4caf50' : pct > 25 ? '#ff9800' : '#f44336'
    if (label) label.textContent = hp + ' HP'
}

function setStatus(msg) {
    var el = document.getElementById('status-msg')
    if (el) el.textContent = msg
}

function showResults(results) {
    var box = document.getElementById('results-box')
    var overlay = document.getElementById('results-overlay')
    if (!box || !overlay) return
    var html = '<h3>Round Results</h3><table>'
    html += '<tr><th>Player</th><th>Distance (ft)</th><th>Damage</th><th>HP left</th></tr>'
    results.forEach(function(p) {
        var elim = p.eliminated ? ' \u2620\ufe0f' : ''
        html += '<tr><td>' + p.username + elim + '</td><td>' + (p.distance_ft != null ? Math.round(p.distance_ft) : '\u2014') + '</td><td>' + (p.damage_taken != null ? p.damage_taken : '\u2014') + '</td><td>' + p.hp + '</td></tr>'
    })
    html += '</table>'
    box.innerHTML = html
    overlay.classList.add('show')
}

function clearResults() {
    var box = document.getElementById('results-box')
    var overlay = document.getElementById('results-overlay')
    if (box) box.innerHTML = ''
    if (overlay) overlay.classList.remove('show')
}

function showObserverOverlay(secondsLeft) {
    var overlay = document.getElementById('observer-overlay')
    var cd = document.getElementById('obs-countdown')
    if (!overlay) return
    if (Math.abs(observerSecondsLeft - secondsLeft) > 2) observerSecondsLeft = secondsLeft
    if (cd) cd.textContent = observerSecondsLeft + 's'
    overlay.classList.add('show')
    if (!observerTimer) {
        observerTimer = setInterval(function() {
            if (observerSecondsLeft > 0) observerSecondsLeft--
            if (cd) cd.textContent = observerSecondsLeft + 's'
        }, 1000)
    }
}

function hideObserverOverlay() {
    var overlay = document.getElementById('observer-overlay')
    if (overlay) overlay.classList.remove('show')
    if (observerTimer) { clearInterval(observerTimer); observerTimer = null }
    observerSecondsLeft = 0
}

// ---- photo swap  ------------------------------------------------------------

function setPhoto(photoPath) {
    if (photoPath === lastLoadedImage) return
    lastLoadedImage = photoPath

    var sky  = document.querySelector('a-sky')
    if(!sky) return

    // Ensures a photo refresh
    var newSrc = '/static/' + photoPath + '?t=' + new Date().getTime()

    sky.setAttribute('src', newSrc)

    
}

// ---- target reveal  ---------------------------------------------------------

function revealTarget(lat, lng) {
    if (lat == null || targetMarker) return  // already revealed this round
    targetMarker = L.marker([lat, lng], {
        icon: L.divIcon({
            className: '',
            html: '<div style="font-size:28px;line-height:1;filter:drop-shadow(0 1px 3px rgba(0,0,0,.7))">🚩</div>',
            iconAnchor: [4, 26]
        })
    }).addTo(map)

    if (userSelection) {
        targetLine = L.polyline(
            [[lat, lng], [userSelection.lat, userSelection.lng]],
            { color: '#d4a017', weight: 2, dashArray: '6 5' }
        ).addTo(map)
        map.fitBounds(targetLine.getBounds(), { padding: [50, 50] })
    } else {
        map.setView([lat, lng], 16)
    }
}

// ---- round state handler ----------------------------------------------------

function handleState(state) {
    // Suppress the generic mid-round join error — the observer overlay handles it instead
    if (state.error && state.error === 'You are not in this round') {
        // ignore — observer overlay will show via polling
    } else if (state.error) {
        setStatus(state.error); return
    }

    // Detect round change — reset UI for new round
    if (currentRoundId !== null && state.round_id !== currentRoundId) {
        submitted = false
        userSelection = null
        wasWaiting = false
        eliminatedShown = false
        hideObserverOverlay()
        if (currentMarker)  { map.removeLayer(currentMarker);  currentMarker  = null }
        if (targetMarker)   { map.removeLayer(targetMarker);   targetMarker   = null }
        if (targetLine)     { map.removeLayer(targetLine);     targetLine     = null }
        clearResults()
        document.getElementById('map-button').disabled = false
        document.getElementById('map-button').textContent = 'Submit Guess'
        if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
        if (interludeTimer) { clearInterval(interludeTimer); interludeTimer = null }
        hideObserverOverlay()
        localSecondsLeft     = 0
        interludeSecondsLeft = 0
    }
    currentRoundId = state.round_id

    // Update photo
    if (state.location && state.location.photo) {
        setPhoto(state.location.photo)
    }

    // Always update player count regardless of waiting state
    var pcEl = document.getElementById('player-count')
    if (pcEl) pcEl.textContent = state.player_count

    // Check for elimination BEFORE any early returns so the modal always fires
    if (!eliminatedShown && state.me && state.me.eliminated && state.me.hp === 0) {
        eliminatedShown = true
        showEliminatedModal()
        return
    }

    // Voluntary leave mid-round (eliminated but hp > 0):
    // Only show the observer overlay when the round is actually running.
    // If the round is reset/waiting, fall through so the server can re-activate us.
    if (state.me && state.me.eliminated && state.me.hp > 0) {
        if (!state.waiting && !state.finished && state.seconds_left > 0) {
            document.getElementById('map-button').disabled = true
            showObserverOverlay(state.seconds_left + 10)
            return
        }
        // Round is waiting/reset — treat as a normal waiting participant (server re-activates)
    }

    // If player is not in this round and it's actively running, show the observer overlay
    if (!state.me && !state.waiting) {
        document.getElementById('map-button').disabled = true
        if (!state.finished) {
            // Active round: next round = seconds_left + interlude window
            showObserverOverlay(state.seconds_left + 10)
        } else {
            // Interlude: next round = next_round_in countdown
            showObserverOverlay((state.next_round_in != null) ? state.next_round_in : 0)
        }
        return
    }

    // Player is in the round (or waiting) — dismiss observer overlay if it was showing
    hideObserverOverlay()
    document.getElementById('map-button').disabled = false

    // Waiting for players
    if (state.waiting) {
        wasWaiting = true
        setStatus('Waiting for one more player to start… (' + state.player_count + '/2)')
        document.getElementById('timer').textContent = '--'
        if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
        return
    }

    // Transition from waiting → active: reset submission state so the player gets a fresh UI
    if (wasWaiting) {
        wasWaiting = false
        submitted = false
        userSelection = null
        if (currentMarker) { map.removeLayer(currentMarker); currentMarker = null }
        if (targetMarker)  { map.removeLayer(targetMarker);  targetMarker  = null }
        if (targetLine)    { map.removeLayer(targetLine);    targetLine    = null }
        if (interludeTimer){ clearInterval(interludeTimer); interludeTimer = null }
        interludeSecondsLeft = 0
        document.getElementById('map-button').disabled = false
        document.getElementById('map-button').textContent = 'Submit Guess'
        clearResults()
    }

    // Seed countdown on first start; only re-sync on large drift (> 2 s) to prevent rubberbanding
    if (!countdownTimer || Math.abs(localSecondsLeft - state.seconds_left) > 2) {
        localSecondsLeft = state.seconds_left
    }
    if (!countdownTimer && state.seconds_left > 0 && !state.finished) {
        document.getElementById('timer').textContent = localSecondsLeft + 's'
        countdownTimer = setInterval(function() {
            if (localSecondsLeft > 0) {
                localSecondsLeft--
                document.getElementById('timer').textContent = localSecondsLeft + 's'
            }
        }, 1000)
    }

    // My stats
    if (state.me) {
        updateHPBar(state.me.hp)
        document.getElementById('streak').textContent = state.me.current_streak
        if (state.me.eliminated) {
            setStatus('You were eliminated! Join again next round.')
            document.getElementById('map-button').disabled = true
        } else if (state.me.guessed) {
            setStatus('Guess submitted! Waiting for round to end…')
            document.getElementById('map-button').disabled = true
            document.getElementById('map-button').textContent = 'Submitted'
        } else {
            setStatus('Place your marker and submit!')
        }
    }

    // Round finished — stop main countdown, show flag + results, run interlude countdown
    if (state.finished) {
        if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
        localSecondsLeft = 0
        document.getElementById('timer').textContent = '0s'

        if (state.results) showResults(state.results)
        if (state.location && state.location.lat != null) {
            revealTarget(state.location.lat, state.location.lng)
        }

        // Interlude countdown
        var nri = (state.next_round_in != null) ? state.next_round_in : 0
        if (nri > 0) {
            if (!interludeTimer || Math.abs(interludeSecondsLeft - nri) > 2) {
                interludeSecondsLeft = nri
            }
            setStatus('Next round starts in ' + interludeSecondsLeft + 's…')
            if (!interludeTimer) {
                interludeTimer = setInterval(function() {
                    if (interludeSecondsLeft > 0) interludeSecondsLeft--
                    setStatus('Next round starts in ' + interludeSecondsLeft + 's…')
                }, 1000)
            }
        } else {
            setStatus('Round over! Waiting for next round…')
        }
    }
}

// ---- eliminated modal ------------------------------------------------------

function showEliminatedModal() {
    // Stop all timers so nothing updates behind the modal
    if (pollTimer)      { clearInterval(pollTimer);      pollTimer      = null }
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
    if (interludeTimer) { clearInterval(interludeTimer); interludeTimer = null }
    document.getElementById('lost-modal').classList.add('show')
}

// ---- leave modal  ----------------------------------------------------------

var pendingLeaveHref = null

function showLeaveModal(href) {
    pendingLeaveHref = href
    document.getElementById('leave-modal').classList.add('show')
}

function hideLeaveModal() {
    document.getElementById('leave-modal').classList.remove('show')
    pendingLeaveHref = null
}

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.nav-leave').forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault()
            showLeaveModal(this.getAttribute('data-href'))
        })
    })

    // Also intercept Sign out — call leave then logout
    var signOutLink = document.querySelector('.btn-logout')
    if (signOutLink) {
        signOutLink.addEventListener('click', function(e) {
            e.preventDefault()
            var dest = this.getAttribute('href')
            navigator.sendBeacon('/lobby/leave')
            window.location.href = dest
        })
    }

    document.getElementById('leave-no').addEventListener('click', hideLeaveModal)

    document.getElementById('lost-home').addEventListener('click', function() {
        // Server already marked us eliminated; just leave cleanly and go home
        navigator.sendBeacon('/lobby/leave')
        window.location.href = '/main'
    })

    document.getElementById('leave-yes').addEventListener('click', function() {
        var dest = pendingLeaveHref || '/main'
        hideLeaveModal()
        // Tell the server to remove us from the lobby, then navigate
        apiFetch('/lobby/leave', 'POST').finally(function() {
            if (pollTimer)      { clearInterval(pollTimer);      pollTimer = null }
            if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
            window.location.href = dest
        })
    })
})

// ---- polling  ---------------------------------------------------------------

// Cover tab-close, refresh, back button — sendBeacon fires even on unload
window.addEventListener('beforeunload', function() {
    navigator.sendBeacon('/lobby/leave')
})

function startPolling() {
    if (pollTimer) return
    pollTimer = setInterval(function() {
        apiFetch('/lobby/state').then(handleState)
    }, 1500)
}

// ---- init -------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", function() {

    map = L.map('map').setView([37.3661, -120.4233], 16)

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 20,
        keepBuffer: 10,
    }).addTo(map)

    map.on('click', function(e) {
        if (submitted) return
        if (currentMarker) map.removeLayer(currentMarker)
        currentMarker = L.marker(e.latlng).addTo(map)
        userSelection = e.latlng
    })

    document.getElementById('map-button').onclick = function() {
        if (!userSelection || submitted) return
        submitted = true
        this.disabled = true
        this.textContent = 'Submitted'
        apiFetch('/lobby/guess', 'POST', { lat: userSelection.lat, lng: userSelection.lng })
            .then(function(data) {
                if (data.error) {
                    setStatus('Error: ' + data.error)
                    submitted = false
                    document.getElementById('map-button').disabled = false
                    document.getElementById('map-button').textContent = 'Submit Guess'
                }
            })
    }

    // Join lobby, then start polling
    apiFetch('/lobby/join', 'POST').then(function(state) {
        handleState(state)
        startPolling()
    })
})