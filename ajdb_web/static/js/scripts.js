'use strict';
function act_snippet_hover_new(){
    var url = $(this).data('snippet');
    var $snippet_container = $('<div class="snippet_container">Előnézet betöltése...</div>');

    var offset = $(this).offset();
    var pane_offset = $('.right_pane_wrapper').offset()
    offset.left -= pane_offset.left;
    offset.top -= pane_offset.top;
    offset.left -= 50;
    offset.top += $(this).height();
    var right_border = $('.right_pane_wrapper').width() - 20;

    $snippet_container.html("Előnézet betöltése...")
    $snippet_container.load(url, function( response, status, xhr ) {
        if ( status == "error" ) {
            $snippet_container.html("Előnézet betöltése sikertelen: " + url)
        } else {
            add_act_snippet_handlers($snippet_container);
        }
        $snippet_container.css({'left': 0});
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
    $snippet_container.appendTo('.right_pane_wrapper');
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
    $root.find("[data-snippet]").each(function() {
        var timeout_obj;
        $(this).hover(
            function(){
                act_snippet_hover_start();
                timeout_obj=setTimeout(act_snippet_hover_new.bind(this), 500);
            },
            function(){
                clearTimeout(timeout_obj);
                act_snippet_hover_end()
            }
        );
    })
}
function scroll_to_hash(){
    var element_id = window.location.hash.slice(1);
    if (!element_id){
        return;
    }
    var element = document.getElementById(element_id);
    if (!element){
        return;
    }
    element.scrollIntoView({block: "center"})
}

function set_up_hash_change_scrolling() {
    $( window ).on('hashchange', scroll_to_hash)
}
