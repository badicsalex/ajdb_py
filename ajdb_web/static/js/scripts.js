'use strict';
function act_snippet_hover_new(){
    var url = $(this).data('snippet');
    var $snippet_container = $('<div class="snippet_container">Előnézet betöltése...</div>');

    var offset = $(this).offset();
    offset.left -= 50;
    offset.top += $(this).height();
    var right_border = Math.max(
        $('#act_container').offset().left + $('#act_container').outerWidth(),
        $(this).offset().left + $(this).outerWidth(),
    )

    $snippet_container.html("Előnézet betöltése...")
    $snippet_container.load(url, function( response, status, xhr ) {
        if ( status == "error" ) {
            $snippet_container.html("Előnézet betöltése sikertelen: " + url)
        } else {
            add_act_snippet_handlers($snippet_container);
        }
        var offset = $snippet_container.offset();
        if (offset.left + $snippet_container.outerWidth() > right_border){
            offset.left = right_border - $snippet_container.outerWidth()
        }
        $snippet_container.css(offset);
    });
    $snippet_container.css(offset);
    $snippet_container.stop();
    $snippet_container.fadeIn(200);
    /* Cancel fadeOut if mouse enters the snippet_container itself */
    /* XXX: This is a hack, basically we use the animation as a way to store state for some time */
    $snippet_container.hover(
        act_snippet_hover_start,
        act_snippet_hover_end,
    );
    $snippet_container.appendTo('#act_container');
}

function act_snippet_hover_start(){
    /* stops hiding all snippet containers */
    $('.snippet_container').stop();
    $('.snippet_container').fadeIn(200);
}

function act_snippet_hover_end(){
    /* hides all snippet containers */
    $('.snippet_container').stop();
    $('.snippet_container').fadeOut(200, function() { $(this).remove(); });
}

function add_act_snippet_handlers($root) {
    console.log("Why tho", $root);
    $root.find("[data-snippet]").each(function() {
        console.log("Added listener to", this);
        $( this ).hover(
            act_snippet_hover_new,
            act_snippet_hover_end
        )
    })
}
