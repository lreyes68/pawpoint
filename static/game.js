//Maps: Lmk which ones you like the best
// https://tile.openstreetmap.org/{z}/{x}/{y}.png
// https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png
// https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png

var map = L.map('map').setView([37.3644754,-120.4231159], 16);
L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    maxZoom: 17,
}).addTo(map);