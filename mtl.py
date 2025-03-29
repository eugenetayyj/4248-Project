# -*- coding: utf-8 -*-
"""Emotion Analysis

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1f5gQZ8pgp1i_kFiz_mFM0FpxHGD6l6zh
"""

# !pip install transformers torch



"""# Loading Libraries"""

import pandas as pd
import numpy as np
import torch

import sklearn
from sklearn.model_selection import train_test_split

import kagglehub

"""# Data Loading"""

sentiment_path = kagglehub.dataset_download("abhi8923shriv/sentiment-analysis-dataset")

print("Path to dataset files:", sentiment_path)

# Load the Data
import kagglehub

# Download latest version
emotion_path = kagglehub.dataset_download("parulpandey/emotion-dataset")

print("Path to dataset files:", emotion_path)

emotion_train_df = pd.read_csv(emotion_path + '/training.csv')
emotion_test_df = pd.read_csv(emotion_path + '/test.csv')
emotion_val_df = pd.read_csv(emotion_path + '/validation.csv')

# Step 2: Load CSV Files
sentiment_train_df = pd.read_csv(f"{sentiment_path}/train.csv", encoding="ISO-8859-1")
sentiment_test_df = pd.read_csv(f"{sentiment_path}/test.csv", encoding="ISO-8859-1")

sentiment_train_df, sentiment_val_df = train_test_split(sentiment_train_df, test_size=0.2, random_state=1, stratify=sentiment_train_df['sentiment'])

# Display the size of each split

print(f"Sentiment: Train size: {len(sentiment_train_df)}, Validation size: {len(sentiment_val_df)}, Testing size: {len(sentiment_test_df)}")
print(f"Emotion: Train size: {len(emotion_train_df)}, Validation size: {len(emotion_val_df)}, Testing size: {len(emotion_test_df)}")

def label_map(label_idx):
  map = {
      0 : "sadness",
      1: "joy",
      2: "love",
      3: "anger",
      4: "fear",
      5: "surprise"
      }
  return map[label_idx]

"""# EDA"""

emotion_train_df.head()
sentiment_train_df.head()

emotion_train_df["word_length"] = emotion_train_df["text"].apply(lambda x: len(x.split()))

emotion_train_df["word_length"].mean() # So We can have 19 token Sentence Embedding
emotion_train_df["word_length"].max()


"""# Model Training (MTL)

## BiLSTM Model
"""

import torch.nn as nn

class BiLSTMModel(nn.Module):
    def __init__(self, bert_hidden_size=768, lstm_hidden_size=256, num_layers=2):
        super(BiLSTMModel, self).__init__()
        self.bilstm = nn.LSTM(
            input_size=bert_hidden_size,
            hidden_size=lstm_hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True
        )

    def forward(self, bert_embeddings):
        lstm_out, _ = self.bilstm(bert_embeddings)  # Shape: [batch, seq_len, 2*lstm_hidden_size]
        return lstm_out

"""Bidrectional LSTM takes BERT embeddings as input and passes them through a BiLSTM to capture sequential dependencies.
BERT-base has 12 transformer layers, 12 attention heads and a hidden size of 768.
We reduce the LSTM hidden sizes to 256 since 768 is too large and will increase computation and memory costs.
We set that the LSTM have 257 hidden units per direction.

Since BiLSTM is bidirectional, hidden sizes doubles.

(we can decrease training time by decreasing lstm hidden size)

## Attention Layer
"""

class Attention(nn.Module):
    def __init__(self, lstm_hidden_size=256):
        super(Attention, self).__init__()
        self.attention_weights = nn.Linear(2 * lstm_hidden_size, 1)

    def forward(self, lstm_output):
        attention_scores = self.attention_weights(lstm_output).squeeze(-1)  # Shape: [batch, seq_len]
        attention_weights = torch.softmax(attention_scores, dim=1)  # Shape: [batch, seq_len]
        context_vector = torch.sum(lstm_output * attention_weights.unsqueeze(-1), dim=1)  # [batch, hidden_dim]
        return context_vector

"""Attention Layer computes attention scores for each time step in the sequence with a linear layer. It creates a weighted sum of LSTM outputs. We use a softmax to convert raw scores into probabilities.
"""

""" Shared Attention Layer"""

class EmotionClassifier(nn.Module):
    def __init__(self, shared_attention, lstm_hidden_size=256, num_classes=6):
        super(EmotionClassifier, self).__init__()
        self.attention = shared_attention  # Shared Attention Mechanism
        self.fc = nn.Linear(2 * lstm_hidden_size, num_classes)

    def forward(self, lstm_output):
        context_vector = self.attention(lstm_output)
        logits = self.fc(context_vector)
        return logits

class SentimentClassifier(nn.Module):
    def __init__(self, shared_attention, lstm_hidden_size=256, num_classes=3):
        super(SentimentClassifier, self).__init__()
        self.attention = shared_attention  # Shared Attention Mechanism
        self.fc = nn.Linear(2 * lstm_hidden_size, num_classes)

    def forward(self, lstm_output):
        context_vector = self.attention(lstm_output)
        logits = self.fc(context_vector)
        return logits

"""## Custom Dataset class"""

from torch.utils.data import DataLoader, Dataset
class EmotionTextClassificationDataset(Dataset): # https://medium.com/@khang.pham.exxact/text-classification-with-bert-7afaacc5e49b
  def __init__(self, data, tokenizer, max_len):
    self.texts = data["text"]
    self.labels = data["label"]
    self.tokenizer = tokenizer
    self.max_len = max_len # Hyperparamter

  def __len__(self):
    return len(self.texts)

  def __getitem__(self, idx):
    text = self.texts[idx]
    label = self.labels[idx]
    tokens = self.tokenizer(text, return_tensors="pt", max_length=self.max_len, padding="max_length", truncation=True)

    return {'input_ids': tokens['input_ids'].flatten(), 'attention_mask': tokens['attention_mask'].flatten(), 'label': torch.tensor(label)}

"""This creates a custom dataset class for training an emotion classification model using BERT embeddings. It helps with efficient data loading and prepares the information in the right format for training a BERT based emotion classifier."""

class SentimentDataset(Dataset):
    def __init__(self, dataframe, tokenizer, max_len):
        self.dataframe = dataframe.dropna(subset=['sentiment'])
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.label_mapping = {"negative": 0, "neutral": 1, "positive": 2}

    def __len__(self):
        return len(self.dataframe)

    def __getitem__(self, index):
        text = str(self.dataframe.iloc[index]["text"])
        sentiment = self.dataframe.iloc[index]["sentiment"]
        
        # Additional safety check
        if pd.isna(sentiment):
            raise ValueError(f"Found NaN sentiment at index {index} after filtering")
            
        label = self.label_mapping[sentiment]
        
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_len,
            return_tensors="pt"
        )

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "label": torch.tensor(label, dtype=torch.long)
        }


"""# Multi Task Training (Shared Attention Layer)"""

# PARAMETERS
bert_model_name = 'distilbert-base-uncased'
MAX_LEN = 48 # https://medium.com/@khang.pham.exxact/text-classification-with-bert-7afaacc5e49b
BATCH_SIZE = 16
NUM_EPOCHS = 10
EMOTION_NUM_CLASSES = 6
SENTIMENT_NUM_CLASSES = 3
LEARNING_RATE = 2e-5
LAMBDA_EMOTION = 0.75 # Equal Contribution to Loss , it's configurable later
LSTM_HIDDEN_SIZE = 256

from transformers import DistilBertTokenizer, DistilBertModel

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

tokenizer = DistilBertTokenizer.from_pretrained(bert_model_name)
bert_model = DistilBertModel.from_pretrained(bert_model_name).to(device)

for param in bert_model.parameters():
    param.requires_grad = False

for param in list(bert_model.parameters())[-4:]:
    param.requires_grad = True

bilstm_model = BiLSTMModel().to(device)
shared_attention = Attention(LSTM_HIDDEN_SIZE)
emotion_model = EmotionClassifier(num_classes=EMOTION_NUM_CLASSES, shared_attention=shared_attention).to(device)
sentiment_model = SentimentClassifier(num_classes=SENTIMENT_NUM_CLASSES, shared_attention=shared_attention).to(device)

#Emotion Data Preparation
emotion_train_dataset = EmotionTextClassificationDataset(emotion_train_df, tokenizer, MAX_LEN)
emotion_test_dataset = EmotionTextClassificationDataset(emotion_test_df, tokenizer, MAX_LEN)
emotion_val_dataset = EmotionTextClassificationDataset(emotion_val_df, tokenizer, MAX_LEN)

emotion_train_dataloader = DataLoader(emotion_train_dataset, batch_size=BATCH_SIZE, shuffle=True)
emotion_val_dataloader = DataLoader(emotion_val_dataset, batch_size=BATCH_SIZE)
emotion_labelstest_dataloader = DataLoader(emotion_test_dataset, batch_size=BATCH_SIZE)


# Sentiment Data Preperations
sentiment_train_dataset = SentimentDataset(sentiment_train_df, tokenizer, MAX_LEN)
sentiment_test_dataset = SentimentDataset(sentiment_test_df, tokenizer, MAX_LEN)
sentiment_val_dataset = SentimentDataset(sentiment_val_df, tokenizer, MAX_LEN)

sentiment_train_dataloader = DataLoader(sentiment_train_dataset, batch_size=BATCH_SIZE, shuffle=True)
sentiment_val_dataloader = DataLoader(sentiment_val_dataset, batch_size=BATCH_SIZE)
sentiment_test_dataloader = DataLoader(sentiment_test_dataset, batch_size=BATCH_SIZE)

"""## Train"""
from torch.cuda.amp import GradScaler, autocast
from itertools import cycle

# GPT Generated : https://chatgpt.com/c/67e107d6-c67c-800f-bb09-a9604e2d68bd

scaler = GradScaler()

def mtl_train(bilstm_model, emotion_model, sentiment_model, bert_model,
          emotion_data_loader, sentiment_data_loader,
          opt_bilstm, opt_emotion, opt_sentiment,
          sched_bilstm, sched_emotion, sched_sentiment,
          criterion, device, lambda_emotion=1.0):
    
    bilstm_model.train()
    emotion_model.train()
    sentiment_model.train()

    for emotion_batch, sentiment_batch in zip(cycle(emotion_data_loader), sentiment_data_loader): # cycle as sentiment data loader is a larger dataset
        opt_bilstm.zero_grad()
        opt_emotion.zero_grad()
        opt_sentiment.zero_grad()

        # Emotion Batch
        input_ids_emotion = emotion_batch['input_ids'].to(device)
        attention_mask_emotion = emotion_batch['attention_mask'].to(device)
        labels_emotion = emotion_batch['label'].to(device)

        with torch.no_grad():
            bert_embeddings_emotion = bert_model(input_ids_emotion, attention_mask=attention_mask_emotion).last_hidden_state

        # Sentiment Batch
        input_ids_sentiment = sentiment_batch['input_ids'].to(device)
        attention_mask_sentiment = sentiment_batch['attention_mask'].to(device)
        labels_sentiment = sentiment_batch['label'].to(device)

        with torch.no_grad():
            bert_embeddings_sentiment = bert_model(input_ids_sentiment, attention_mask=attention_mask_sentiment).last_hidden_state

        with autocast():  # Enable mixed precision
            # Emotion Loss
            lstm_output_emotion = bilstm_model(bert_embeddings_emotion)
            logits_emotion = emotion_model(lstm_output_emotion)
            loss_emotion = criterion(logits_emotion, labels_emotion)

            # Sentiment Loss
            lstm_output_sentiment = bilstm_model(bert_embeddings_sentiment)
            logits_sentiment = sentiment_model(lstm_output_sentiment)
            loss_sentiment = criterion(logits_sentiment, labels_sentiment)

            # Weighted Total Loss
            total_loss = loss_sentiment + lambda_emotion * loss_emotion

        scaler.scale(total_loss).backward()
        scaler.step(opt_bilstm)
        scaler.step(opt_emotion)
        scaler.step(opt_sentiment)
        scaler.update()

        sched_bilstm.step()
        sched_emotion.step()
        sched_sentiment.step()

"""## Evaluate"""

from sklearn.metrics import accuracy_score

# GPT Generated: https://chatgpt.com/c/67e107d6-c67c-800f-bb09-a9604e2d68bd

def mtl_evaluate(bilstm_model, emotion_model, sentiment_model, bert_model,
             emotion_data_loader, sentiment_data_loader, device):
    """
    Evaluates both the emotion and sentiment classification models.

    Args:
        bilstm_model: BiLSTM model
        emotion_model: Emotion classification model
        sentiment_model: Sentiment classification model
        bert_model: Pretrained BERT model
        emotion_data_loader: DataLoader for emotion classification
        sentiment_data_loader: DataLoader for sentiment classification
        device: Computation device (CPU/GPU)

    Returns:
        Tuple (emotion_accuracy, sentiment_accuracy)
    """
    bilstm_model.eval()
    emotion_model.eval()
    sentiment_model.eval()

    # --------------------- Emotion Classification ---------------------
    emotion_preds = []
    emotion_labels = []

    with torch.no_grad():
        for batch in emotion_data_loader:
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            labels = batch['label'].to(device)

            with torch.no_grad():
                bert_embeddings = bert_model(input_ids, attention_mask=attention_mask).last_hidden_state

            lstm_output = bilstm_model(bert_embeddings)
            logits = emotion_model(lstm_output)
            _, curr_preds = torch.max(logits, dim=1)

            emotion_preds.extend(curr_preds.cpu().tolist())
            emotion_labels.extend(labels.cpu().tolist())

    emotion_accuracy = accuracy_score(emotion_labels, emotion_preds)

    # --------------------- Sentiment Classification ---------------------
    sentiment_preds = []
    sentiment_labels = []

    with torch.no_grad():
        for batch in sentiment_data_loader:
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            labels = batch['label'].to(device)

            with torch.no_grad():
                bert_embeddings = bert_model(input_ids, attention_mask=attention_mask).last_hidden_state

            lstm_output = bilstm_model(bert_embeddings)
            logits = sentiment_model(lstm_output)
            _, curr_preds = torch.max(logits, dim=1)

            sentiment_preds.extend(curr_preds.cpu().tolist())
            sentiment_labels.extend(labels.cpu().tolist())

    sentiment_accuracy = accuracy_score(sentiment_labels, sentiment_preds)

    return emotion_accuracy, sentiment_accuracy

"""## Training Process"""
from torch.optim import AdamW
from transformers import get_linear_schedule_with_warmup
opt_bilstm = torch.optim.Adam(bilstm_model.parameters(), lr=LEARNING_RATE)
opt_emotion = torch.optim.Adam(emotion_model.parameters(), lr=LEARNING_RATE)
opt_sentiment = torch.optim.Adam(sentiment_model.parameters(), lr=LEARNING_RATE)
total_steps = max(len(emotion_train_dataloader), len(sentiment_train_dataloader)) * NUM_EPOCHS
sched_bilstm = get_linear_schedule_with_warmup(opt_bilstm, num_warmup_steps=0, num_training_steps=total_steps)
sched_emotion = get_linear_schedule_with_warmup(opt_emotion, num_warmup_steps=0, num_training_steps=total_steps)
sched_sentiment = get_linear_schedule_with_warmup(opt_sentiment, num_warmup_steps=0, num_training_steps=total_steps)
criterion = nn.CrossEntropyLoss()


"""We define the optimizers for the BiLSTM & Emotion Classifier while applying linear learning rate decay for both models. We choose cross entropy loss since this is most common for multi class classification."""
for epoch in range(NUM_EPOCHS):
    print(f"\nEpoch {epoch + 1}/{NUM_EPOCHS}")

    mtl_train(bilstm_model, emotion_model, sentiment_model, bert_model,
              emotion_train_dataloader, sentiment_train_dataloader,
              opt_bilstm, opt_emotion, opt_sentiment,
              sched_bilstm, sched_emotion, sched_sentiment,
              criterion, device, lambda_emotion=LAMBDA_EMOTION)  # Adjust lambda as needed

    # Evaluate both tasks separately
    emotion_acc, sentiment_acc = mtl_evaluate(
        bilstm_model, emotion_model, sentiment_model, bert_model,
        emotion_val_dataloader, sentiment_val_dataloader, device
    )

    print(f"Validation Accuracy - Emotion: {emotion_acc:.4f}")
    print(f"Validation Accuracy - Sentiment: {sentiment_acc:.4f}")

"""# Model Saving"""
import os
os.makedirs("results", exist_ok=True)

EMOTION_MODEL = "results/emotion_model_reduced.pth"
BILSTM_MODEL = "results/bilstm_model.pth"

# Save model state dicts
torch.save(emotion_model.state_dict(), EMOTION_MODEL)
torch.save(bilstm_model.state_dict(), BILSTM_MODEL)

"""# Evaluation"""


emotion_acc, sentiment_acc = mtl_evaluate(
    bilstm_model, emotion_model, sentiment_model, bert_model,
    emotion_labelstest_dataloader, sentiment_test_dataloader, device
)

print(f"Test Accuracy - Emotion: {emotion_acc:.4f}")
print(f"Test Accuracy - Sentiment: {sentiment_acc:.4f}")