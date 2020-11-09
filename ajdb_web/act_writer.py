# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Callable, Any, Iterable, Dict, Tuple, Union, Optional
from flask import Blueprint, abort, render_template, url_for
import attr

from hun_law.structure import \
    SubArticleElement, QuotedBlock, BlockAmendmentContainer, \
    StructuralElement, Subtitle, \
    Article, Reference, OutgoingReference
from hun_law.utils import EMPTY_LINE, Date

from ajdb.structure import ActWM, ArticleWMProxy
from ajdb.database import Database
from ajdb.utils import reference_as_hungarian_string
from .html_utils import HtmlWriter


@attr.s(slots=True, frozen=True, auto_attribs=True)
class HtmlWriterContext:
    current_ref: Reference
    _all_incoming_refs: Dict[Reference, Tuple[Reference, ...]] = {}
    _structural_element_anchors: Dict[StructuralElement, str] = {}
    _inside_ba: bool = False
    _filter_ref: Optional[Reference] = None

    @property
    def incoming_refs(self) -> Tuple[Reference, ...]:
        return self._all_incoming_refs.get(self.current_ref, ())

    def update_ref(self, element: Union[Article, SubArticleElement]) -> 'HtmlWriterContext':
        if self._inside_ba:
            return self
        new_ref = element.relative_reference.relative_to(self.current_ref)
        return attr.evolve(self, current_ref=new_ref)

    def went_inside_block_amendment(self) -> 'HtmlWriterContext':
        return attr.evolve(self, inside_ba=True)

    @property
    def id_string(self) -> str:
        if self._inside_ba:
            return ''
        return "ref_" + self.current_ref.relative_id_string

    def get_anchor_for_structural_element(self, se: StructuralElement) -> str:
        return self._structural_element_anchors.get(se, '')

    def is_current_allowed_by_filter(self) -> bool:
        if self._filter_ref is None:
            return True
        return self.current_ref.contains(self._filter_ref) or self._filter_ref.contains(self.current_ref)


HtmlWriterFn = Callable[[HtmlWriter, Any, HtmlWriterContext], None]
all_act_html_writers = []


def act_html_writer(fn: HtmlWriterFn) -> HtmlWriterFn:
    global all_act_html_writers
    all_act_html_writers.append((fn.__annotations__['element'], fn))
    return fn


def write_html_any(writer: HtmlWriter, element: Any, ctx: HtmlWriterContext) -> None:
    for written_type, writer_fn in all_act_html_writers:
        if isinstance(element, written_type):
            writer_fn(writer, element, ctx)
            break
    else:
        raise TypeError("Unknown type to write HTML for: {}".format(type(element)))


@act_html_writer
def write_html_structural_element(writer: HtmlWriter, element: StructuralElement, ctx: HtmlWriterContext) -> None:
    anchor = ctx.get_anchor_for_structural_element(element)
    with writer.div("se_" + element.__class__.__name__.lower(), id=anchor):
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
    result = result + "#" + "ref_" + ref.first_in_range().relative_id_string
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
        links_to_create.append((outgoing_ref.start_pos, outgoing_ref.end_pos, absolute_ref))

    links_to_create.sort()
    prev_end = 0
    for start, end, ref in links_to_create:
        assert start >= prev_end
        assert end > start
        writer.write(text[prev_end:start])
        href = get_href_for_ref(ref)
        if ref.article is not None:
            snippet_href = url_for('act.snippet', identifier=ref.act, ref_str=ref.relative_id_string)
        else:
            snippet_href = ''
        with writer.tag('a', href=href, data_snippet=snippet_href):
            writer.write(text[start:end])
        prev_end = end
    writer.write(text[prev_end:])


@act_html_writer
def write_html_block_amendment(writer: HtmlWriter, element: BlockAmendmentContainer, ctx: HtmlWriterContext) -> None:
    ctx = ctx.went_inside_block_amendment()
    if element.intro:
        with writer.div('blockamendment_text'):
            writer.write("(" + element.intro + ")")

    with writer.div('blockamendment_quote'):
        writer.write('„')

    with writer.div('blockamendment_container'):
        assert element.children is not None
        for child in element.children:
            write_html_any(writer, child, ctx)

    with writer.div('blockamendment_quote'):
        writer.write('”')

    if element.wrap_up:
        with writer.div('blockamendment_text'):
            writer.write("(" + element.wrap_up + ")")


def write_html_sub_article_element_children(writer: HtmlWriter, element: SubArticleElement, ctx: HtmlWriterContext) -> None:
    if element.intro:
        with writer.div('sae_text'):
            write_text_with_ref_links(writer, element.intro, ctx.current_ref, element.outgoing_references or ())

    assert element.children is not None
    for child in element.children:
        write_html_any(writer, child, ctx)

    if element.wrap_up:
        with writer.div('sae_text'):
            # TODO: write links too
            writer.write(element.wrap_up)


@act_html_writer
def write_html_sub_article_element(writer: HtmlWriter, element: SubArticleElement, ctx: HtmlWriterContext) -> None:
    ctx = ctx.update_ref(element)
    if not ctx.is_current_allowed_by_filter():
        return

    header = element.header_prefix(element.identifier)
    with writer.div('sae_container', id=ctx.id_string):
        with writer.div('sae_identifier'):
            writer.write(header)
        if ctx.incoming_refs:
            snippet_href = url_for(
                'act.incoming_refs',
                identifier=ctx.current_ref.act,
                ref_str=ctx.current_ref.relative_id_string
            )
            with writer.div('sae_incoming', data_snippet=snippet_href):
                writer.write('⇇ {}'.format(len(ctx.incoming_refs)))
        with writer.div('sae_body'):
            if element.text:
                with writer.div('sae_text'):
                    write_text_with_ref_links(writer, element.text, ctx.current_ref, element.outgoing_references or ())
            else:
                write_html_sub_article_element_children(writer, element, ctx)


@act_html_writer
def write_html_quoted_block(writer: HtmlWriter, element: QuotedBlock, _ctx: HtmlWriterContext) -> None:
    with writer.tag('blockquote'):
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
def write_html_article(writer: HtmlWriter, element: Article, ctx: HtmlWriterContext) -> None:
    ctx = ctx.update_ref(element)
    if not ctx.is_current_allowed_by_filter():
        return

    header = '{}. §'.format(element.identifier)
    with writer.div('article_container', id=ctx.id_string):
        with writer.div('article_identifier'):
            writer.write(header)
        with writer.div('article_body'):
            if element.title:
                with writer.div('article_title'):
                    writer.write('[{}]'.format(element.title))

            for child in element.children:
                write_html_any(writer, child, ctx)


@act_html_writer
def write_html_article_proxy(writer: HtmlWriter, element: ArticleWMProxy, ctx: HtmlWriterContext) -> None:
    write_html_any(writer, element.article, ctx)


def write_html_act_body(writer: HtmlWriter, act: ActWM, ctx: HtmlWriterContext) -> None:
    with writer.div('act_title'):
        writer.write(act.identifier)
        writer.br()
        writer.write(act.subject)
    if act.preamble:
        with writer.div('preamble'):
            writer.write(act.preamble)
    for child in act.children:
        write_html_any(writer, child, ctx)


def write_toc_entries(
    writer: HtmlWriter,
    ses: Tuple[StructuralElement, ...],
    structural_element_anchors: Dict[StructuralElement, str]
) -> Tuple[StructuralElement, ...]:
    """ Returns the rest of the ses """
    current_type = type(ses[0])
    while ses and not isinstance(ses[0], current_type.PARENT_TYPES):
        with writer.tag('li', _class='toc_elem'):
            with writer.tag('a', href="#" + structural_element_anchors.get(ses[0], '')):
                if ses[0].title:
                    writer.write(ses[0].title)
                else:
                    writer.write(ses[0].formatted_identifier)
            ses = ses[1:]
            if ses and not isinstance(ses[0], current_type.PARENT_TYPES + (current_type,)):
                with writer.tag('ul', _class='toc_elem_container'):
                    ses = write_toc_entries(writer, ses, structural_element_anchors)
    return ses


def write_table_of_contents(writer: HtmlWriter, act: ActWM, structural_element_anchors: Dict[StructuralElement, str]) -> None:
    ses = tuple(c for c in act.children if isinstance(c, StructuralElement))
    if ses:
        with writer.tag('ul', _class='toc_elem_container'):
            write_toc_entries(writer, ses, structural_element_anchors)
    else:
        writer.write('Nem található szerkezeti elem')


def generate_structural_element_anchors(act: ActWM) -> Dict[StructuralElement, str]:
    return {
        c: 'seref_{}'.format(i) for i, c in enumerate(act.children) if isinstance(c, StructuralElement)
    }


_blueprint = Blueprint('act', __name__)


@_blueprint.route('/act/<identifier>')
def single_act(identifier: str) -> str:
    act_set = Database.load_act_set(Date.today())
    if not act_set.has_act(identifier):
        abort(404)
    act = act_set.act(identifier)
    incoming_references = act_set.get_incoming_references(act.identifier)
    structural_element_anchors = generate_structural_element_anchors(act)
    writer = HtmlWriter()
    context = HtmlWriterContext(
        current_ref=Reference(act.identifier),
        all_incoming_refs=incoming_references,
        structural_element_anchors=structural_element_anchors
    )
    write_html_act_body(writer, act, context)
    act_str = writer.get_str()

    writer = HtmlWriter()
    write_table_of_contents(writer, act, structural_element_anchors)
    toc_str = writer.get_str()
    return render_template('act.html', act=act, act_str=act_str, toc_str=toc_str)


@_blueprint.route('/snippet/<identifier>/<ref_str>')
def snippet(identifier: str, ref_str: str) -> str:
    act_set = Database.load_act_set(Date.today())
    try:
        act = act_set.act(identifier)

        ref = Reference.from_relative_id_string(ref_str).relative_to(Reference(identifier))
        if ref.article is None:
            raise ValueError()

        if not act.at_reference(ref):
            raise KeyError()
    except ValueError:
        abort(400)
    except KeyError:
        abort(404)

    paragraphs_ref = Reference(ref.act, ref.article)
    writer = HtmlWriter()
    context = HtmlWriterContext(paragraphs_ref.first_in_range(), filter_ref=ref)
    for element in act.at_reference(paragraphs_ref):
        write_html_any(writer, element, context)
    return writer.get_str()


@_blueprint.route('/incoming_refs/<identifier>/<ref_str>')
def incoming_refs(identifier: str, ref_str: str) -> str:
    act_set = Database.load_act_set(Date.today())
    try:
        to_ref = Reference.from_relative_id_string(ref_str).relative_to(Reference(identifier))
        references = act_set.get_incoming_references(identifier)[to_ref]
    except ValueError:
        abort(400)
    except KeyError:
        abort(404)
    writer = HtmlWriter()
    writer.write("{} bejövő hivatkozás:".format(len(references)))
    for from_ref in references:
        writer.br()
        href = get_href_for_ref(from_ref)
        snippet_href = url_for('act.snippet', identifier=from_ref.act, ref_str=from_ref.relative_id_string)
        with writer.tag('a', href=href, data_snippet=snippet_href):
            writer.write(reference_as_hungarian_string(from_ref))
    return writer.get_str()


ACT_BLUEPRINT = _blueprint
