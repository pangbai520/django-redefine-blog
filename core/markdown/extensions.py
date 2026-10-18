from django.conf import settings
from markdown.extensions import Extension
from .inline.hyperlinks import LinkIconProcessor
from .inline.buttons import BUTTON_RE, ButtonInlineProcessor
from .inline.formatting import STRIKETHROUGH_RE, StrikethroughInlineProcessor
from .blocks.code_block import CodeBlockProcessor
from .blocks.notel import NotelProcessor
from .blocks.redefine_tags import ButtonsProcessor, FoldingProcessor, NoteProcessor, TabsProcessor
from .tree.image_caption import ImageCaptionProcessor, RawImageCaptionPostprocessor
from .tree.lazyload import LazyLoadProcessor, RawImageLazyLoadPostprocessor
from .tree.delete_mask import DeleteMaskPostprocessor
from .tree.task_lists import TaskListProcessor
from .preprocessors import TabMarkerPreprocessor

class Extensions(Extension):
    def __init__(
        self,
        *args,
        hyperlink_icon=True,
        image_caption=False,
        lazyload=True,
        mermaid=False,
        delete_mask=False,
        internal_hosts=None,
        **kwargs,
    ):
        self.hyperlink_icon = hyperlink_icon
        self.image_caption = image_caption
        self.lazyload = lazyload
        self.mermaid = mermaid
        self.delete_mask = delete_mask
        self.internal_hosts = internal_hosts or ()
        super().__init__(*args, **kwargs)

    def extendMarkdown(self, md):
        md.preprocessors.register(TabMarkerPreprocessor(md), 'redefine_tab_markers', 35)
        md.treeprocessors.register(
            LinkIconProcessor(
                md,
                add_icon=self.hyperlink_icon,
                internal_hosts=self.internal_hosts,
            ),
            'link_icon',
            15,
        )
        if self.image_caption:
            md.treeprocessors.register(ImageCaptionProcessor(md), 'image_caption', 14)
            md.postprocessors.register(
                RawImageCaptionPostprocessor(md),
                'redefine_raw_image_caption',
                8,
            )
        if self.lazyload:
            md.treeprocessors.register(LazyLoadProcessor(md), 'redefine_lazyload', 13)
            md.postprocessors.register(
                RawImageLazyLoadPostprocessor(md),
                'redefine_raw_image_lazyload',
                9,
            )
        md.treeprocessors.register(TaskListProcessor(md), 'redefine_task_lists', 11)
        if self.delete_mask:
            # run after Markdown restores raw HTML, so authored <del> tags and
            # generated strikethroughs follow the same site setting
            md.postprocessors.register(
                DeleteMaskPostprocessor(md),
                'redefine_delete_mask',
                15,
            )

        md.inlinePatterns.register(
            ButtonInlineProcessor(BUTTON_RE, md),
            'redefine_button',
            175,
        )
        md.inlinePatterns.register(
            StrikethroughInlineProcessor(
                STRIKETHROUGH_RE,
                md,
                masked=self.delete_mask,
            ),
            'redefine_strikethrough',
            174,
        )

        code_processor = CodeBlockProcessor(md.parser)
        code_processor.mermaid = self.mermaid
        md.parser.blockprocessors.register(code_processor, 'code_block', 105)
        md.parser.blockprocessors.register(TabsProcessor(md.parser), 'redefine_tabs', 104)
        md.parser.blockprocessors.register(NoteProcessor(md.parser), 'redefine_note', 104)
        md.parser.blockprocessors.register(NotelProcessor(md.parser), 'notel', 105)
        md.parser.blockprocessors.register(FoldingProcessor(md.parser), 'redefine_folding', 104)
        md.parser.blockprocessors.register(ButtonsProcessor(md.parser), 'redefine_buttons', 104)


def get_extensions(site=None):
    hyperlink_icon = getattr(site, 'hyperlink_icon', True) if site is not None else True
    image_caption = getattr(site, 'article_image_description', False) if site is not None else False
    lazyload = getattr(site, 'article_lazyload', True) if site is not None else True
    mermaid = getattr(site, 'mermaid_enabled', False) if site is not None else False
    delete_mask = getattr(site, 'delete_mask', False) if site is not None else False
    internal_hosts = {
        "localhost",
        "127.0.0.1",
        "::1",
        *getattr(settings, "ALLOWED_HOSTS", ()),
    }
    return [
        'nl2br',
        "markdown.extensions.tables",
        "markdown.extensions.attr_list",
        "markdown.extensions.toc",
        Extensions(
            hyperlink_icon=hyperlink_icon,
            image_caption=image_caption,
            lazyload=lazyload,
            mermaid=mermaid,
            delete_mask=delete_mask,
            internal_hosts=internal_hosts,
        ),
    ]
