(function () {
    var images = [
        '/static/photos/MercedBG1.jpg',
        '/static/photos/MercedBG2.jpg',
        '/static/photos/MercedBG3.jpg'
    ];

    var STORAGE_KEY = 'pawpoint_bg_index';
    var INTERVAL_MS = 20000;

    var currentIndex = parseInt(localStorage.getItem(STORAGE_KEY) || '0') % images.length;
    var activeLayer = 0;

    function layer(n) {
        return document.getElementById('bg-layer-' + n);
    }

    function applyImage(index, instant) {
        var next = 1 - activeLayer;
        var old = activeLayer; // capture before mutation
        layer(next).style.backgroundImage = "url('" + images[index] + "')";

        if (instant) {
            layer(old).style.opacity = '0';
            layer(next).style.opacity = '1';
        } else {
            layer(next).style.opacity = '1';
            setTimeout(function () {
                layer(old).style.opacity = '0'; // fade out the OLD layer, not the new one
            }, 50);
        }

        activeLayer = next;
        currentIndex = index;
        localStorage.setItem(STORAGE_KEY, index);
    }

    document.addEventListener('DOMContentLoaded', function () {
        applyImage(currentIndex, true);

        setInterval(function () {
            applyImage((currentIndex + 1) % images.length, false);
        }, INTERVAL_MS);
    });
}());
