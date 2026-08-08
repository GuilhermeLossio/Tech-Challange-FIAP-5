from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import gradio as gr

MODEL_ID = os.getenv("MODEL_ID", "tencent/HunyuanImage-3.0")
MODEL_DIR = os.getenv("MODEL_DIR", "HunyuanImage-3")


@lru_cache(maxsize=1)
def _load_model() -> Any:
    from huggingface_hub import snapshot_download
    from transformers import AutoModelForCausalLM

    model_path = Path(MODEL_DIR)
    if not model_path.exists():
        snapshot_download(repo_id=MODEL_ID, local_dir=str(model_path))

    model = AutoModelForCausalLM.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        device_map="auto",
    )
    load_tokenizer = getattr(model, "load_tokenizer", None)
    if callable(load_tokenizer):
        load_tokenizer(str(model_path))
    return model


def _save_result(result: Any, output_path: Path) -> str:
    image = result[0] if isinstance(result, (list, tuple)) and result else result
    save = getattr(image, "save", None)
    if callable(save):
        save(output_path)
        return str(output_path)
    if isinstance(image, bytes):
        output_path.write_bytes(image)
        return str(output_path)
    raise gr.Error("The model returned an unsupported image result.")


def generate(prompt: str, seed: int) -> str:
    prompt = prompt.strip()
    if not prompt:
        raise gr.Error("Prompt is required.")
    model = _load_model()
    output_path = Path("/tmp") / f"hunyuan_image_{abs(int(seed))}.png"
    for method_name in ("generate_image", "text_to_image", "infer"):
        method = getattr(model, method_name, None)
        if callable(method):
            result = method(prompt=prompt, seed=int(seed))
            return _save_result(result, output_path)
    raise gr.Error("Loaded model does not expose a supported image-generation method.")


with gr.Blocks(title="ECloe HunyuanImage 3 Demo") as demo:
    gr.Markdown("# ECloe HunyuanImage 3 Demo")
    gr.Markdown("Generate demo-safe ECloe Market product images with `tencent/HunyuanImage-3.0`.")
    with gr.Row():
        prompt = gr.Textbox(
            label="Prompt",
            lines=5,
            value=(
                "Demo-safe ecommerce product photo, isolated marketplace catalog asset, "
                "clean studio lighting, no text, no logos, square image."
            ),
        )
        seed = gr.Number(label="Seed", value=426, precision=0)
    image = gr.Image(label="Generated image", type="filepath", format="png")
    button = gr.Button("Generate", variant="primary")
    button.click(generate, inputs=[prompt, seed], outputs=image, api_name="generate")


if __name__ == "__main__":
    demo.queue(max_size=8).launch()
