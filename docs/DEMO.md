# Walkthrough: mask, review, restore

[Watch the MP4](media/maskele-demo-24s.mp4) · [English captions](media/maskele-demo.en.srt) · [Türkçe altyazı](media/maskele-demo.tr.srt) · [Try the browser app](https://temurcanbulut.github.io/maskele/)

The 24.5-second silent walkthrough shows four actual captures of the updated application running its Python engine locally through Pyodide. These UI changes are published at commit [77cd61d](https://github.com/temurcanbulut/maskele/commit/77cd61db9ad4872b9ed13320660e51874e88bcba). Caption bars explain the workflow; editorial holds are not response-time measurements. The first three shots crop away the next section and add neutral letterboxing. No application result, control or state is fabricated.

| Time | Actual workflow state |
| --- | --- |
| 0.0–6.5s | Paste a synthetic support record; repeated IPs use the same token. |
| 6.5–11.5s | Enter Anka-42 in the manual masking field after it is missed automatically. |
| 11.5–17.0s | Add and commit it: six matches correspond to five distinct values. |
| 17.0–24.5s | Restore five tokens in a manually written sample reply locally. |

All input values are invented fixtures. No customer record, real credential, provider response or LLM request appears. Detection is incomplete; inspect the masked text before sharing it. Consistent tokens do not guarantee anonymity.

The MP4 is H.264, 1248×702 at 24fps, with no audio. English/Turkish SRT and VTT captions accompany it. [Provenance and SHA256](media/demo-provenance.json) records the UI version and media hashes. Visual QA was performed by AI; `human_verified` is false. The older [GIF](images/workflow.gif) and [original frame record](images/workflow-source.json) remain historical references.

[Privacy boundaries](../SECURITY.md) · [Architecture and runtime differences](ARCHITECTURE.md).
