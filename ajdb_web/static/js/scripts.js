'use strict';
function act_snippet_hover_start(){
    var url = $(this).data('snippet');

    var offset = $(this).offset();
    offset.top += $(this).height();

    var $snippet_container = $('#snippet_container');
    $snippet_container.html("Előnézet betöltése...")
    $snippet_container.load(url, function( response, status, xhr ) {
        if ( status == "error" ) {
            $snippet_container.html("Előnézet betöltése sikertelen: " + url)
        }
    });
    $snippet_container.css(offset);
    $snippet_container.stop();
    $snippet_container.fadeIn(200);
}

function act_snippet_hover_end(){
    $('#snippet_container').stop();
    $('#snippet_container').fadeOut(200);
}

function add_act_snippet_handlers() {
    $("a[data-snippet]").each(function($element) {
        $( this ).hover(
            act_snippet_hover_start,
            act_snippet_hover_end
        )
    })
    /* Cancel fadeOut if mouse enters the snippet_container itself */
    /* XXX: This is a hack, basically we use the animation as a way to store state for some time */
    $("#snippet_container").hover(
        function(){$(this).stop(); $(this).fadeIn(200);},
        function(){$(this).stop(); $(this).fadeOut(200);},
    )
}
