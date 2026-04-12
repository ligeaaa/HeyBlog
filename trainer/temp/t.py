from transformers import BertTokenizerFast, BertForSequenceClassification, pipeline
import torch

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Device: {device}")

model_name = "CrabInHoney/urlbert-tiny-v4-malicious-url-classifier"
tokenizer = BertTokenizerFast.from_pretrained(model_name)
model = BertForSequenceClassification.from_pretrained(model_name)
model.to(device)

classifier = pipeline(
    "text-classification",
    model=model,
    tokenizer=tokenizer,
    device=0 if torch.cuda.is_available() else -1,
    return_all_scores=True
)

test_urls = [
    "wikiobits.com/Obits/TonyProudfoot",
    "http://www.824555.com/app/member/SportOption.php?uid=guest&langx=gb",
]

label_mapping = {
    "LABEL_0": "benign",
    "LABEL_1": "defacement",
    "LABEL_2": "malware",
    "LABEL_3": "phishing"
}

for url in test_urls:
    results = classifier(url)
    print(f"\nURL: {url}")
    for result in results: 
        label = result['label']
        score = result['score']
        friendly_label = label_mapping.get(label, label)
        print(f"{friendly_label}, %: {score:.4f}")
