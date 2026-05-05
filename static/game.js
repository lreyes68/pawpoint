//Maps: Lmk which ones you like the best
// https://tile.openstreetmap.org/{z}/{x}/{y}.png
// https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png
// https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png

var map
var currentMarker
var userSelection = null
var submitted = false

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
    .then(function(data) {
        L.marker([data.target.lat, data.target.lng], {color: 'red'}).addTo(map)
        const polyline = L.polyline([[data.target.lat, data.target.lng],userSelection], {color: 'red'}).addTo(map)
      
        map.fitBounds(polyline.getBounds())
    })
}

document.addEventListener("DOMContentLoaded", function() {
    map = L.map('map').setView([37.3661,-120.4233], 16);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 20,
        keepBuffer: 10,
    }).addTo(map);

    //TODO: Make sure user cannot click after submit button is clicked.
    function onMapClick(e) {
        if(!submitted){
        
            if(currentMarker) {
                map.removeLayer(currentMarker)
            }
            currentMarker = L.marker(e.latlng).addTo(map)

            userSelection = e.latlng
        }
    }

    var submitButton = document.getElementById("map-button")

    submitButton.onclick = function(){
        if (userSelection !== null && !submitted) {
            submitted = true
            sendGuess(userSelection)

        }
    }

    map.on('click', onMapClick);
})