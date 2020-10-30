# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Callable, Any, Iterable

from flask import Blueprint, abort, render_template, url_for

from hun_law.structure import \
    SubArticleElement, QuotedBlock, BlockAmendmentContainer, \
    StructuralElement, Subtitle, \
    Article, Reference, OutgoingReference, Act
from hun_law.utils import EMPTY_LINE, Date

from ajdb.database import Database
from .html_utils import HtmlWriter

HtmlWriterFn = Callable[[HtmlWriter, Any, Reference], None]
all_act_html_writers = []


def act_html_writer(fn: HtmlWriterFn) -> HtmlWriterFn:
    global all_act_html_writers
    all_act_html_writers.append((fn.__annotations__['element'], fn))
    return fn


def write_html_any(writer: HtmlWriter, element: Any, parent_ref: Reference) -> None:
    for written_type, writer_fn in all_act_html_writers:
        if isinstance(element, written_type):
            writer_fn(writer, element, parent_ref)
            break
    else:
        raise TypeError("Unknown type to write HTML for: {}".format(type(element)))


@act_html_writer
def write_html_structural_element(writer: HtmlWriter, element: StructuralElement, _parent_ref: Reference) -> None:
    with writer.div("se_" + element.__class__.__name__.lower()):
        writer.write(element.formatted_identifier)
        if isinstance(element, Subtitle):
            writer.write(" ")
        else:
            writer.br()
        writer.write(element.title)


def get_href_for_ref(ref: Reference) -> str:
    result = ''
    if ref.act is not None:
        result = url_for('act.single_act', identifier=ref.act)
    result = result + "#" + ref.relative_id_string
    return result


def write_text_with_ref_links(
    writer: HtmlWriter,
    text: str,
    current_ref: Reference,
    outgoing_references: Iterable[OutgoingReference]
) -> None:
    links_to_create = []
    for outgoing_ref in outgoing_references:
        absolute_ref = outgoing_ref.reference.relative_to(current_ref)
        links_to_create.append((outgoing_ref.start_pos, outgoing_ref.end_pos, get_href_for_ref(absolute_ref)))

    links_to_create.sort()
    prev_end = 0
    for start, end, href in links_to_create:
        assert start >= prev_end
        assert end > start
        writer.write(text[prev_end:start])
        with writer.tag('a', href=href):
            writer.write(text[start:end])
        prev_end = end
    writer.write(text[prev_end:])


@act_html_writer
def write_html_block_amendment(writer: HtmlWriter, element: BlockAmendmentContainer, _parent_ref: Reference) -> None:
    # Quick hack to signify that IDs are not needed further on
    current_ref = Reference("EXTERNAL")
    if element.intro:
        with writer.div('blockamendment_text'):
            writer.write("(" + element.intro + ")")

    with writer.div('blockamendment_quote'):
        writer.write('„')

    with writer.div('blockamendment_container'):
        assert element.children is not None
        for child in element.children:
            write_html_any(writer, child, current_ref)

    with writer.div('blockamendment_quote'):
        writer.write('”')

    if element.wrap_up:
        with writer.div('blockamendment_text'):
            writer.write("(" + element.wrap_up + ")")


@act_html_writer
def write_html_sub_article_element(writer: HtmlWriter, element: SubArticleElement, parent_ref: Reference) -> None:
    current_ref = element.relative_reference.relative_to(parent_ref)
    id_string = current_ref.relative_id_string
    # Quick hack so that we don't have duplicate ids within block amendments
    if current_ref.act == "EXTERNAL":
        id_string = ''
    element_type_as_text = element.__class__.__name__.lower()
    with writer.div('{}_id'.format(element_type_as_text), id=id_string):
        writer.write(element.header_prefix(element.identifier))

    if element.text:
        with writer.div('{}_text'.format(element_type_as_text)):
            write_text_with_ref_links(writer, element.text, current_ref, element.outgoing_references or ())
    else:
        if element.intro:
            with writer.div('{}_text'.format(element_type_as_text)):
                write_text_with_ref_links(writer, element.intro, current_ref, element.outgoing_references or ())

        assert element.children is not None
        for child in element.children:
            write_html_any(writer, child, current_ref)

        if element.wrap_up:
            with writer.div('{}_text'.format(element_type_as_text)):
                write_text_with_ref_links(writer, element.wrap_up, current_ref, element.outgoing_references or ())


@act_html_writer
def write_html_quoted_block(writer: HtmlWriter, element: QuotedBlock, parent_ref: Reference) -> None:
    parent_type = parent_ref.last_component_with_type()[1]
    assert parent_type is not None
    with writer.tag('blockquote', _class='quote_in_{}'.format(parent_type.__name__.lower())):
        indent_offset = min(l.indent for l in element.lines if l != EMPTY_LINE)
        for index, l in enumerate(element.lines):
            padding = int((l.indent-indent_offset) * 2)
            if padding < 0:
                padding = 0
            with writer.div('quote_line', style='padding-left: {}px;'.format(padding)):
                text = l.content
                if index == 0:
                    text = '„' + text
                if index == len(element.lines) - 1:
                    text = text + "”"
                if not text:
                    text = chr(0xA0)  # Non breaking space, so the div is forced to display.
                writer.write(text)


@act_html_writer
def write_html_article(writer: HtmlWriter, element: Article, parent_ref: Reference) -> None:
    current_ref = element.relative_reference.relative_to(parent_ref)
    id_string = current_ref.relative_id_string
    # Quick hack so that we don't have duplicate ids within block amendments
    if current_ref.act == "EXTERNAL":
        id_string = ''
    with writer.div('article_id', id=id_string):
        writer.write('{}. §'.format(element.identifier))

    if element.title:
        with writer.div('article_title'):
            writer.write('[{}]'.format(element.title))

    for child in element.children:
        write_html_any(writer, child, current_ref)

    with writer.div('space_after_article'):
        pass


def write_html_act(writer: HtmlWriter, act: Act) -> None:
    with writer.div('act_title'):
        writer.write(act.identifier)
        writer.br()
        writer.write(act.subject)
    if act.preamble:
        with writer.div('preamble'):
            writer.write(act.preamble)
    current_ref = Reference()
    for child in act.children:
        write_html_any(writer, child, current_ref)


_blueprint = Blueprint('act', __name__)


@_blueprint.route('/act/<identifier>')
def single_act(identifier: str) -> str:
    act_set = Database.load_act_set(Date.today())
    if not act_set.has_act(identifier):
        abort(404)
    act = act_set.act(identifier).to_simple_act()
    writer = HtmlWriter()
    write_html_act(writer, act)
    act_str = writer.get_str()
    return render_template('act.html', act=act, act_str=act_str)


ACT_BLUEPRINT = _blueprint
