//Maps: Lmk which ones you like the best
// https://tile.openstreetmap.org/{z}/{x}/{y}.png
// https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png
// https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png


document.addEventListener("DOMContentLoaded", function() {
    var map = L.map('map').setView([37.3644754,-120.4231159], 16);
    var currentMarker

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 20,
    }).addTo(map);

    function onMapClick(e) {
        if(currentMarker) {
            map.removeLayer(currentMarker)
        }

        currentMarker = L.marker(e.latlng).addTo(map)
    }

    map.on('click', onMapClick);
})