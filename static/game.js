//Maps: Lmk which ones you like the best
// https://tile.openstreetmap.org/{z}/{x}/{y}.png
// https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png
// https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png

var map
var currentMarker
var userSelection = null
var submitted = false

//Function to send guess to server
function sendGuess(latlng){
    fetch('/guess', {
        method: 'POST',
        credentials: 'include', //needed for jwt_required()
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
    .then(function(data) { //Processes data sent back from server

        //Adds target marker and creates line between guess and target
        L.marker([data.target.lat, data.target.lng]).addTo(map)
        const polyline = L.polyline([[data.target.lat, data.target.lng],userSelection], {color: 'red'}).addTo(map)
        
        //Moves map to center the guess and target
        map.fitBounds(polyline.getBounds())
    })
}

//Handles clicking on map
document.addEventListener("DOMContentLoaded", function() {

    //Loads the map, we can change coordinates to where we want it centered. I have it centered at CTK quad
    map = L.map('map').setView([37.3661,-120.4233], 16);

    //Map api
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 20,
        keepBuffer: 10,
    }).addTo(map);

    //When user clicks on map
    function onMapClick(e) {

        //If the user hasnt submitted a guess, the marker moves to latest click
        if(!submitted){
        
            if(currentMarker) {
                map.removeLayer(currentMarker)
            }
            currentMarker = L.marker(e.latlng).addTo(map)

            //coordinates of guess: e.latlng gives [xxx.xxx, xxx.xxx]
            userSelection = e.latlng
        }
    }

    var submitButton = document.getElementById("map-button")

    //Once submit button is clicked, if a guess was made we send the guess to the server.
    submitButton.onclick = function(){
        if (userSelection !== null && !submitted) {
            submitted = true
            sendGuess(userSelection)

        }
    }

    map.on('click', onMapClick);
})