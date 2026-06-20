# VibeFlow speech-accuracy (Whisper) benchmark

Hard sentences (numbers, acronyms, names, homophones, jargon) rendered as FAST TTS to stress the models.

## Accuracy + speed summary

| Model (tier) | Size | clips | avg WER | median WER | avg sec/clip |
|---|---|---|---|---|---|
| base (Fast) | ~150 MB | 18 | 15.0% | 20.0% | 0.8 |
| small (Balanced) | ~500 MB | 18 | 11.9% | 13.3% | 2.4 |
| large-v3 (Accurate) | ~3 GB | 18 | 11.1% | 13.3% | 16.0 |
| distil-large-v3 ((bonus)) | ~1.5 GB | 18 | 15.9% | 16.7% | 10.5 |

_WER = Word Error Rate (lower is better). 0% = perfect._

## Transcriptions by case

### Case 1

**Reference:** The server at 192.168.0.14 returned HTTP error 503 after 4500 milliseconds.

- **base** (WER 0%, 0.84s): The server at 192.168.0.14 returned HTTP error 503 after 4500 milliseconds.
- **small** (WER 0%, 2.34s): The server at 192.168.0.14 returned HTTP error 503 after 4500 milliseconds.
- **large-v3** (WER 0%, 12.78s): The server at 192.168.0.14 returned HTTP error 503 after 4500 milliseconds.
- **distil-large-v3** (WER 14%, 11.28s): The server at 192.168.0.14 returned HTTP error 503 after 4,500 milliseconds.

### Case 2

**Reference:** Deploy the Kubernetes pod using kubectl apply and verify the YAML configuration.

- **base** (WER 25%, 0.76s): Deploy the cube urnets pod using cubex-apply and verify the YAML configuration.
- **small** (WER 25%, 2.35s): Deploy the Qbutternets pod using kubexlaplie and verify the YAML configuration.
- **large-v3** (WER 17%, 12.82s): Deploy the KubeEarnets pod using KubeExtra Apply and verify the YAML configuration.
- **distil-large-v3** (WER 17%, 9.93s): Deploy the Kubeternets pod using Kubeckl apply and verify the YAML configuration.

### Case 3

**Reference:** Vamsi and Nguyen reviewed the Qwen and Gemma benchmark results on Tuesday.

- **base** (WER 17%, 0.74s): VAMSI and Win reviewed the Quinn and Gemma benchmark results on Tuesday.
- **small** (WER 17%, 2.38s): VAMSY and Nguyen reviewed the Quen and Gemma benchmark results on Tuesday.
- **large-v3** (WER 17%, 13.54s): Vamzee and Nguyen reviewed the Quen and Gemma benchmark results on Tuesday.
- **distil-large-v3** (WER 8%, 10.08s): Vamsi and Nguyen reviewed the Quinn and Gemma benchmark results on Tuesday.

### Case 4

**Reference:** They're driving to their house over there to debate the principal's core principle.

- **base** (WER 0%, 0.75s): They're driving to their house over there to debate the principal's core principle.
- **small** (WER 0%, 2.25s): They're driving to their house over there to debate the principal's core principle.
- **large-v3** (WER 0%, 13.85s): They're driving to their house over there to debate the principal's core principle.
- **distil-large-v3** (WER 0%, 10.01s): They're driving to their house over there to debate the principal's core principle.

### Case 5

**Reference:** The patient was prescribed 250 milligrams of amoxicillin to be taken twice daily.

- **base** (WER 0%, 0.74s): The patient was prescribed 250 milligrams of amoxicillin to be taken twice daily.
- **small** (WER 8%, 2.26s): The patient was prescribed 250 mg of amoxicillin to be taken twice daily.
- **large-v3** (WER 8%, 14.28s): The patient was prescribed 250 mg of amoxicillin to be taken twice daily.
- **distil-large-v3** (WER 0%, 10.11s): The patient was prescribed 250 milligrams of amoxicillin to be taken twice daily.

### Case 6

**Reference:** The meeting on March 3rd at 2:45 PM was rescheduled to the 17th at 11:30 AM.

- **base** (WER 28%, 0.77s): The meeting on March 3 at 2.45pm was rescheduled to the 17th at 11.30am.
- **small** (WER 28%, 2.44s): The meeting on March 3 at 2.45pm was rescheduled to the 17th at 11.30am.
- **large-v3** (WER 28%, 15.02s): The meeting on March 3 at 2.45pm was rescheduled to the 17th at 11.30am.
- **distil-large-v3** (WER 28%, 10.07s): The meeting on March 3 at 2.45 p.m. was rescheduled to the 17th at 11.30 a.m.

### Case 7

**Reference:** Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.

- **base** (WER 0%, 0.75s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.
- **small** (WER 0%, 2.31s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.
- **large-v3** (WER 0%, 14.45s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.
- **distil-large-v3** (WER 0%, 9.98s): Add 2.5 liters of water and heat it to 350 degrees Fahrenheit for 25 minutes.

### Case 8

**Reference:** Third quarter revenue grew 18.7 percent to 4.2 million dollars year over year.

- **base** (WER 20%, 0.75s): 3rd quarter revenue grew 18.7% to $4.2 million year over year
- **small** (WER 13%, 2.33s): Third quarter revenue grew 18.7% to $4.2 million year over year.
- **large-v3** (WER 13%, 14.6s): Third quarter revenue grew 18.7% to $4.2 million year over year.
- **distil-large-v3** (WER 13%, 10.03s): Third quarter revenue grew 18.7% to $4.2 million year over year.

### Case 9

**Reference:** Run npm install, then npx vite build, and commit the changes to the main branch.

- **base** (WER 13%, 0.77s): Run npm install, then npxveet build, and commit the changes to the main branch.
- **small** (WER 13%, 2.34s): Run npm install, then npxv build, and commit the changes to the main branch.
- **large-v3** (WER 13%, 14.65s): Run npm install, then np xvit build, and commit the changes to the main branch
- **distil-large-v3** (WER 13%, 10.58s): Run NPM install, then NPXVet build, and commit the changes to the main branch.

### Case 10

**Reference:** Please email john.doe@example.com and copy the team at support@acme.io.

- **base** (WER 21%, 0.79s): Please email john.do at example.com and copy the team at support at acme.io
- **small** (WER 21%, 2.36s): Please email john.doe at example.com and copy the team at support at akmi.io
- **large-v3** (WER 14%, 16.53s): Please email john.doe at example.com and copy the team at support at acme.io.
- **distil-large-v3** (WER 21%, 11.14s): Please email john.do at example.com and copy the team at support at acme.io.

### Case 11

**Reference:** We ordered croissants, gnocchi, and a jalapeno quesadilla for the office lunch.

- **base** (WER 8%, 0.81s): We ordered croissants, knocky, and a jalapeno quesadilla for the office lunch.
- **small** (WER 8%, 2.44s): We ordered croissants, Naki, and a jalapeno quesadilla for the office lunch.
- **large-v3** (WER 0%, 14.67s): We ordered croissants, gnocchi, and a jalapeno quesadilla for the office lunch.
- **distil-large-v3** (WER 25%, 10.92s): We ordered croissons, Naki, and a jalapeno caesidia for the office lunch.

### Case 12

**Reference:** The NASDAQ fell 2.3 percent while the S&P 500 rose 0.8 percent on Friday.

- **base** (WER 12%, 0.78s): The NASDAQ fell 2.3% while the S&P 500 rose 0.8% on Friday.
- **small** (WER 0%, 2.43s): The Nasdaq fell 2.3 percent while the S&P 500 rose 0.8 percent on Friday.
- **large-v3** (WER 12%, 13.45s): The Nasdaq fell 2.3% while the S&P 500 rose 0.8% on Friday.
- **distil-large-v3** (WER 24%, 10.73s): The NASDAQ fell 2.3% while the SNP 500 rose 0.8% on Friday.

### Case 13

**Reference:** Mitochondria produce ATP through the process of oxidative phosphorylation.

- **base** (WER 33%, 0.75s): might occur to produce ATP through the process of oxidative phosphorylation.
- **small** (WER 0%, 2.3s): mitochondria produce ATP through the process of oxidative phosphorylation.
- **large-v3** (WER 0%, 11.89s): mitochondria produce ATP through the process of oxidative phosphorylation.
- **distil-large-v3** (WER 11%, 10.48s): mitochondria produce ATP through the process of oxidative phospholation.

### Case 14

**Reference:** Call me at 555 867 5309 or dial extension 42 any time after 5 PM.

- **base** (WER 27%, 0.79s): Call me at 555-867-5309 or dial extension 42 anytime after 5pm.
- **small** (WER 27%, 2.35s): Call me at 555-867-5309 or dial extension 42 anytime after 5pm.
- **large-v3** (WER 27%, 13.65s): Call me at 555-867-5309 or dial extension 42 anytime after 5 p.m.
- **distil-large-v3** (WER 27%, 10.56s): Call me at 555-867-5309 or dial extension 42 anytime after 5 p.m.

### Case 15

**Reference:** The API uses OAuth 2.0 with JWT tokens sent over HTTPS on port 8443.

- **base** (WER 20%, 0.87s): The API uses OAuth 2.0 with JWT token sent over HTTPS on port 8,443.
- **small** (WER 7%, 2.45s): The API uses OAuth 2.0 with JWT token sent over HTTPS on port 8443.
- **large-v3** (WER 7%, 14.96s): The API uses OAuth 2.0 with JWT token sent over HTTPS on port 8443.
- **distil-large-v3** (WER 27%, 10.81s): The API uses OAuth 2.0 with JWT token sent over HTTP on port 8,443.

### Case 16

**Reference:** Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.

- **base** (WER 0%, 0.74s): Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.
- **small** (WER 0%, 2.32s): Notwithstanding the circumstances, the Committee unanimously ratified the amended proposal.
- **large-v3** (WER 0%, 43.29s): Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.
- **distil-large-v3** (WER 0%, 10.58s): Notwithstanding the circumstances, the committee unanimously ratified the amended proposal.

### Case 17

**Reference:** Schedule the cron job for 0 30 4 every Sunday and log to var slash log slash app.

- **base** (WER 22%, 0.77s): Schedule the cron job for 034 every Sunday and log to our slash log slash app.
- **small** (WER 17%, 2.44s): Schedule the cron job for 0.34 every Sunday and log to our slash log slash app.
- **large-v3** (WER 22%, 18.21s): Schedule the cron job for 034 every Sunday and log to our slash log slash app.
- **distil-large-v3** (WER 28%, 10.9s): Schedule the cron job for 034 every Sunday and log tovar slash log slash app.

### Case 18

**Reference:** Doctor Smith said the acetaminophen dosage should not exceed 3000 milligrams per day.

- **base** (WER 23%, 0.77s): Dr. Smith said the acetaminophen dosage should not exceed 3,000 milligrams per day.
- **small** (WER 31%, 2.67s): Dr. Smith said the acetaminophen dosage should not exceed 3,000 mg per day.
- **large-v3** (WER 23%, 14.81s): Dr. Smith said the acetaminophen dosage should not exceed 3,000 milligrams per day.
- **distil-large-v3** (WER 31%, 10.67s): Dr. Smith said the acetaminifin dosage should not exceed 3,000 milligrams per day.
