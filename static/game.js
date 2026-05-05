//Maps: Lmk which ones you like the best
// https://tile.openstreetmap.org/{z}/{x}/{y}.png
// https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png
// https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png

function sendGuess(latlng){
    fetch('/guess', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            lat: latlng.lat,
            lang: latlng.lng
        })
    })
    .then(function(response) {
        return response.json();
    })
}

document.addEventListener("DOMContentLoaded", function() {
    var map = L.map('map').setView([37.3661,-120.4233], 16);
    var currentMarker
    var userSelection = null

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 20,
        keepBuffer: 10,
    }).addTo(map);

    function onMapClick(e) {
        if(currentMarker) {
            map.removeLayer(currentMarker)
        }
        currentMarker = L.marker(e.latlng).addTo(map)

        userSelection = e.latlng
    }

    var submitButton = document.getElementById("map-button")

    submitButton.onclick = function(){
        if (userSelection !== null) {
            sendGuess(userSelection)
        }
    }

    map.on('click', onMapClick);
})