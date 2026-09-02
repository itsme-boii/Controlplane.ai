import json
import os

from datasets import load_dataset


def main():
    print("Loading dataset...")
    # Load a dataset of prompt injections. We use the train split.
    dataset = load_dataset("deepset/prompt-injections", split="train")

    # We filter only the injected prompts (label == 1)
    injections = dataset.filter(lambda example: example["label"] == 1)

    # Take a sample of 250 injections to keep the embedding bank small and fast
    sample = injections.select(range(min(250, len(injections))))

    # Extract just the text strings
    prompts = [example["text"] for example in sample]

    data_dir = "controlplane_detectors/data"
    os.makedirs(data_dir, exist_ok=True)

    output_path = os.path.join(data_dir, "injection_bank.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2)

    print(f"Saved {len(prompts)} injections to {output_path}")


if __name__ == "__main__":
    main()
