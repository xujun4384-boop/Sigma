# Multi-Agent Presentation Creation

> This document guides how to create presentations by coordinating multiple agents when page count exceeds 20.

## File Isolation
Create an independent working directory for the current PPT task, and write all artifacts into this directory:
```
<ppt-dir>/
├── design.md          # Design document
├── outline.md         # Outline document
├── <ppt-name>.pptd   # PPT main entry file
└── pages/             # .page file directory
```

## Workflow

### step1: File Reading
- If the user has uploaded files, **read them in full** first, including images, documents, websites, etc. Do not proceed until all files have been fully read.

### step2: User Requirements and Audience Analysis
- Analyze the user's requirements for the final presentation, including:
  1. Language requirements: Does the user have a specific language preference? If not, match the language of the user's input
  2. Prerequisites: Are there reference materials from previous workflows? Such as artifacts in various formats from previous processes (markdown, docx, etc.), search results, or no prerequisites at all
  3. Page count requirements: Does the user have specific page count requirements? e.g., 20, 50, or even 100 pages.
    * If the user has no specific page count requirements, the page count should be determined based on prerequisites, e.g.: collected 20 papers -> generate 20/40/60 content pages + n cover/TOC/chapter pages; collected 100 company profiles -> generate 100 content pages + n cover/TOC/chapter pages, etc.
    * If there are no prerequisites, the page count can be left tentative and decided based on subsequent research content
  4. Content requirements: Does the user have specific charts, data, conclusions, or topic requirements, or specific requirements for language style?
  5. Visual requirements: Does the user have specific design style or color scheme requirements, or specific requirements for images, charts, and other elements?
  6. Audience analysis: Analyze the target audience the user is likely addressing, including age, profession, expertise level, expected content presentation style, etc.

### step3: Determine Working Mode
Based on the user requirements analyzed in step2, determine the content mode and visual mode to enter:
- Content mode:
  1. Summary mode: e.g., user uploads a long document (such as a paper, report, etc.) and asks you to generate a PPT based on it; or previous workflows have generated prerequisite documents that need to be referenced for PPT creation (Note: not all uploaded document scenarios are summary mode; only when the content is **highly complete** should you enter summary mode. Otherwise, based on the document content, you should enter outline mode or search mode.)
  2. Outline mode: e.g., user provides an outline with per-page content planning; or provides a highly structured outline (e.g., complete, hierarchical titles, etc.)
  3. Search mode: User provides no outline or long document, only a topic and related requirements, requiring you to search and supplement content

- Visual mode:
  1. Replication/Reference mode: e.g., user uploads images or websites and asks you to replicate them as PPT; or asks to create a PPT in the same style as reference screenshots
  2. Creative mode: No visual references provided, only style/color requirements or nothing at all

### step4: Content Design
- Based on the content mode determined in step3, enter the corresponding content design workflow, **use the write_file tool** to complete the content design document `<ppt-dir>/outline.md`
  1. Summary mode: Read guideline/content/summary_mode.md for more information
  2. Outline mode: Read guideline/content/outline_mode.md for more information
  3. Search mode: Read guideline/content/search_mode.md for more information
  * outline.md is the core content reference for subsequent presentation generation. It must be persisted using the write_file tool for step6 to read and reference. It is strictly forbidden to only output it in the conversation.

### step5: Visual Design
- Based on the visual mode determined in step3, enter the corresponding visual design workflow, **use the write_file tool** to complete the visual design document `<ppt-dir>/design.md`
  1. Replication/Reference mode: Read guideline/design/reference_mode.md for more information
  2. Creative mode: Read guideline/design/creative_mode.md for more information
  * design.md is the core visual reference for subsequent presentation generation. It must be persisted using the write_file tool for step6 to read and reference. It is strictly forbidden to only output it in the conversation.
- Note: **Visual design should be based on content — less content does NOT mean simpler design; it actually demands higher-end, more refined aesthetics!** The less content there is, the more the design needs to elevate the sense of sophistication. If the content is in outline mode, or each page has relatively little text, you need more decorative elements, images, and finer grid layouts to ensure a premium visual experience.

### step6: Generate Presentation
- Refer to the image supplementation strategy below to add appropriate illustrations to the presentation
- Generate the presentation based on the visual design and content outline. Ensure full compliance with the format requirements defined in format/pptd.md during generation.
- If outline.md contains annotated source URLs, use `<a href="url">` in the PPTD to link key data, cited viewpoints, etc. to the original source pages, making it easy for the audience to trace and verify.

#### 1. Main Agent Creates .pptd File
- Read the format requirements defined in format/pptd.md, and generate the main entry .pptd file under `<ppt-dir>/`
- This file defines the presentation's theme and plans the pages

#### 2. Create .page Files

> **Condition check**: Only when creating **1 PPT** with **<= 20 pages**, the main agent may write all .page files directly, proceeding directly to step7. In all other cases (multiple PPTs, or a single PPT with more than 20 pages), delegate to sub-agents.

**For <= 20 pages (main agent direct mode):**
- Generate .page files in page order according to outline.md
- **Use parallel write_file calls**: Write as many .page files as possible in a single response

**For > 20 pages (sub-agent mode):**
1. Based on the number of .page files to be created, use the `sub_agent` tool to create sub-agents. The following information must be declared when creating:
  * The identity is a **pptx page building sub-agent** (not the main agent)
  * The main agent has already completed the design.md design document, outline.md content outline document, and the pptname.pptd main entry file design
  * The goal is to build x .page files
  * The following content must be read before execution for guidance:
    a. {skill_path}/format/pptd.md: Format definition of the pptd file
    b. {skill_path}/guideline/design/profiles/xxxx.md: Corresponding preset scene reference
    c. The design.md file produced by the main agent
    d. The .pptd file produced by the main agent
    e. The outline.md file produced by the main agent
    f. {skill_path}/guideline/subagent/attention.md: Notes for creating presentations

  * Tasks the sub-agent should handle: assign 20 pages of production tasks to each sub-agent. The following information must be declared when assigning tasks:
    * The sub-agent's content writing mode: Based on the current situation, inform the sub-agent which writing guide to read
      * Summary writing (read {skill_path}/guideline/subagent/summary_writing.md): Used when there is a clear content source
      * Search writing (read {skill_path}/guideline/subagent/search_writing.md): Used when there are no document deposits and the sub-agent needs to search and expand content on its own
    * Which pages should be created: Simply inform the file names of the pages to be created in the .pptd main entry file
    * Declare documents that the sub-agent needs to reference — **Primary principle: For any file already persisted to disk, always pass the file path and let the sub-agent read the full content on its own. It is strictly prohibited to summarize, abstract, or paraphrase file content before passing it to the sub-agent!** Any form of summarization leads to information loss — the sub-agent receives degraded information, significantly reducing generation quality. Specific rules:
      - If reference content already exists as files (whether markdown/docx/txt produced by previous workflows, or intermediate files generated by the main agent), directly provide the file paths and their purpose
      - If reference content only exists in the main agent's context (e.g., search results, user supplements in conversation, not written to files), you should **first use write_file to persist the content as files**, then pass the file paths to the sub-agent

> Task assignment logic: Prioritize assigning similar pages to the same sub-agent: e.g., one sub-agent handles all covers, table of contents, and chapter transition pages, while other n sub-agents handle content pages, etc.; rather than having each sub-agent handle both chapter transition pages and content pages.
>
> Use `run_in_background=true` to run sub-agents in the background and enable concurrency.
>
> In later turns, if you need to modify pages created or edited by that sub-agent, choose the working mode based on workload:
> - Very small workload: the main agent modifies/creates the pages directly
> - Medium workload: use the `resume` parameter to let the original agent modify them
> - Large workload (such as a complete restructuring): use a new sub-agent but tell the new sub-agent about previous progress

#### Image Supplementation Strategy
1. Prioritize extracting suitable images from user-uploaded content (such as Word, PDF, PPTX, etc.) as presentation illustrations
2. If the user has not provided sufficient and suitable images, and has not explicitly requested no additional images, you should by default use image generation tools to prepare appropriate illustrations for the presentation
3. Image generation strategy:
  - Generated images should reference the visual design style in design.md, pursuing movie poster or magazine cover level visual impact and aesthetics
  - Write detailed prompts that match the design style (color scheme, mood, composition). Using English prompts typically yields higher quality results
  - Do not generate data charts (line charts, bar charts, pie charts, etc. — use chart elements), table screenshots (use table elements), icons (use icon elements), or diagrams (flowcharts, hierarchy diagrams, architecture diagrams, etc. — use shape+text+line element combinations)
4. Retry strategy: If initial generation results are of poor quality, you must try different prompts or refine the style description. ***Never use low-quality images or substitute with gradients/solid colors/placeholders!***
  - Do not replace image slots that originally need images with solid color backgrounds, gradient fills, shape compositions, etc. just because generation is difficult
5. Image usage guidelines
  - Cover/chapter/closing pages: Full-bleed high-quality images with gradient masks are recommended to create visual impact
  - Content pages: Images should be directly relevant to the page content; avoid purely decorative images
  - Image sizing: Set sizes appropriately based on layout needs; cropping is preferred; avoid stretching unless necessary

#### Text Box Size Estimation
- Text box wrapping control: When generating PPTD, you **must** explicitly set `wrap: false` for every text box intended to display on a single line: title text boxes, labels/badges, data numbers, navigation elements, etc.
- Line height calculation: The actual rendered line height of a font is approximately fontSize x 1.3 (ascent + descent in font metrics), not fontSize itself. Therefore:
  * Single-line text height = fontSize x max(lineHeight, 1.3)
  * X-line text height = fontSize x max(lineHeight, 1.3) x X
  * Example: fontSize=14, lineHeight=1.2 -> single-line height = 14 x 1.3 = 18.2px, not 14 x 1.2 = 16.8px.
- Text width calculation:
  * Chinese character width is approximately fontSize; English/digit width is approximately fontSize x 0.5~0.6
  * With letter spacing: total width is approximately fontSize x Y + letterSpacing x (Y - 1)
- Text box size calculation for required content
  * Use the above methods to calculate text width and line height, combined with paragraph spacing settings, to estimate the required text box dimensions (width and height)
  * Ensure text box dimensions match actual text content size: oversized content will cause text overflow; undersized content will cause page whitespace

#### Overall Page Layout Control
- Set body area content appropriately: After removing fixed page elements (title, footnotes, etc.), the body content area layout should also be evenly and reasonably distributed:
  * Avoid excessive content concentration: Avoid content height being far less than the page body area height (e.g., body area height 500px, content only 200px). Use font size, element spacing, number of decorative elements, etc. to ensure actual content height is close to the page body area height
  * Avoid top-heavy bottom-empty: When content is sparse and genuinely far less than the body area height, ensure the actual content area is centered within the body area with equal top and bottom whitespace. Content concentrated at the top with excessive bottom whitespace is strictly forbidden
- Maintain grid alignment: Ensure all elements are properly aligned
  * For left-right layouts, ensure left and right content grids are aligned with consistent heights: avoid one side extending to the bottom while the other only fills halfway
  * For top-bottom layouts, ensure content has equal left and right whitespace: avoid content concentrated on the left with large right-side whitespace

### step7: Check .pptd Files

**In sub-agent mode**: Each sub-agent checks its own assigned pages using `--pages` before completion. The main agent then runs the full check after all sub-agents finish.

**In direct mode**: The main agent runs the full check directly.

1. Check
- After all sub-agents complete their .page file creation (or after direct generation), the **convert_pptx** tool must be used to check the files, ensuring no format errors or unexpected overflow issues:
- The main agent should run the checker **without the `--pages` parameter** to perform a full check on all pages (sub-agents have already checked their own pages using `--pages`; this serves as the final full verification):
- Call `convert_pptx(input_path="<ppt-name>.pptd", action="check")` to run the check
- The checker will check for the following issues, divided into Error and Warning categories:
  * Format check: Whether YAML syntax is valid, required fields are present, field values are valid, elementId is unique within pages, etc.
  * Data validation: Color format and reference validity, elements exceeding page boundaries, shapeName validity, chart/table data completeness
  * Layout detection: Text occlusion, text box misalignment with underlying containers
  * Text box content detection: Text width/height overflow, text underfill

2. Fix
- Fix all ERRORs first: These issues will cause conversion failures and must be fixed
- Then handle WARNINGs: **PPTD has no auto-correction logic. Every WARNING reported by the checker means a corresponding visual issue (truncation, occlusion, overflow, etc.) will appear in the final PPTX.** Therefore, WARNINGs must be fixed by default unless you can clearly determine that the WARNING is part of the intended design (e.g., decorative elements intentionally extending beyond the canvas). If skipping a WARNING, you must explain the reason.
- **Fix in parallel**: **You must call the edit_file tool in parallel as much as possible in a single response**, fixing issues across multiple files at once rather than fixing files one by one sequentially.
  1. TextOverflowWarning (text overflow): The space required by text content exceeds the text box space, causing content truncation (must fix)
  2. TextOcclusionWarning (text occlusion): Text is occluded by other elements (images/shapes/text boxes, etc.), making text unreadable
  3. TextDriftWarning (text drift): The text box is pierced through by other elements, or is not fully aligned with underlying shapes, images, etc.
  4. TextUnderfillWarning (text underfill): The text box is too large or the font size is too small, resulting in large blank areas within the text box, often causing unexpected whitespace on the page
  5. BoundsOutsideWarning (out of bounds): The element is partially or fully outside the canvas dimensions, making it partially or fully invisible

3. Re-verification
- After fixing, **re-run the checker** and **review the complete output** (using grep/sed to filter is forbidden). Focus on the Summary at the bottom, checking the count of each issue type to confirm all ERRORs have been eliminated and all unexpected WARNINGs have been addressed. If residual issues remain, continue fixing and repeat verification until the Summary shows `0 errors, 0 warnings`. **Using grep to filter and only viewing/fixing partial issues is strictly forbidden!**

#### Fix Precautions
- Maintain margins: After adjusting element bounds, check whether reasonable spacing is still maintained between the element and page edges, adjacent elements, and bottom elements. Do not forget to leave appropriate margins when adjusting bounds to resolve text overflow or whitespace issues, causing text boxes to be pressed against edges and losing original margins. **Fixed bounds should maintain consistent margins with other elements of the same type on the page.**
- Do not move common element positions: Common elements on pages (such as navigation bars, titles, corner badges, etc.) should maintain consistent positions across pages. When layout issues exist, prioritize adjusting content layout to avoid subtle differences in common elements across pages (such as inconsistent heights, font sizes, etc.; intentionally designed special layouts are exceptions)
- Ensure content alignment: When adjusting element A, ensure related elements are adjusted in sync. Common situations include:
  * Adjusted text box size but did not sync the background color/card size beneath the text box
  * Adjusted element A's position but did not sync attached decorative elements (such as decoration bars, progress bars, etc.) in size and position, causing misalignment

#### Text Overflow Fix Strategy
When the checker reports TextOverflowWarning, fix in the order suggested by the checker:
- Height overflow:
  1. Condense text: Compress expressions, merge points, remove secondary content
  2. Reduce font size: Decrease content font size, line spacing, paragraph spacing, etc.
  3. Expand text box height: If the above approaches are not feasible and there is space below the text box, increase the bounds height to accommodate the content. But be careful not to introduce overlap or drift issues
- Width overflow:
  1. Condense text: Shorten text content, reducing the content volume to the percentage suggested by the checker
  2. Switch to multi-line: Set `wrap: true` to enable auto-wrapping, and adjust text box height and layout accordingly
> **It is forbidden to excessively reduce font size to eliminate overflow, causing large blank areas within the text box** -- this is more detrimental to aesthetics than slight overflow.

### step8: Convert and Deliver the .pptx File
- **Convert in place — do not copy the .pptd file alone.** .pptd is the entry of a multi-file project and strictly depends on sibling directories such as `pages/`, `images/` (and possibly `svg/`). Running `cp xxx.pptd /some/other/dir/` will cause the CLI conversion tool to fail because dependencies cannot be found.
- After checks pass, call the `convert_pptx` tool:
  - `convert_pptx(input_path="<ppt-name>.pptd", output_path="<ppt-name>.pptx", action="check_convert")`
- The tool will perform final check + conversion in one call. Fix any reported errors and retry.
- Deliver the generated .pptx file to the user, and summarize the presentation's content highlights, core insights, specific structure, and other key information.

## Additional Notes

### Multi-Presentation Generation
When the user requests creating multiple presentations, **you must adopt a generate-all-first, then check-one-by-one strategy!** That is: the main agent first completes all PPTs' design.md, outline.md, and .pptd files, then collectively creates sub-agents to assign all PPTs' .page production tasks, and only proceeds to unified checking, fixing, and delivery after all presentations are created. **Never complete one PPT and immediately check, fix, and deliver it before creating the next PPT**.

### Parallel Writing
**You must call the write_file tool in parallel as much as possible in a single response.** Specifically:
- After generating the .pptd main file, write as many .page files as possible in parallel in the same response
- Each .page file is an independent write_file call with no dependencies, and should all be issued in the same response
