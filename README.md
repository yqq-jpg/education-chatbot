Core Features
•Intelligent dialogue: Integrate with model API and support context understanding
Then, the linking model stores the user's question and the robot's answer in the database. In subsequent questions, it selects the most recent conversation and uses text vectorization to match the historical records in the database that best match the current question, using them as historical prompts for the language model, giving the robot a human like memory function.
•File processing: Supports uploading and parsing of files in multiple formats
•Image recognition: supports image uploading and intelligent analysis
•Emotion analysis: Real time analysis of user emotions and adjustment of response strategies
•User Profile: Automatically build and update user interest profiles
•News push: supports multilingual news aggregation and push
•Search function: Integrated network search capability

technology stack
flask+mysql
Model:
•HuggingFace(image processing)
•SentenceTransformer(Text vectorization)
•BERT(Sentiment analysis)
•BaiDu api(chat)/ Deploy ollama locally and use it to run the model(deepseek_r1:1.5b)
I have marked the historical records, but the local 1.5b model doesn't work very well. If I switch to the 8b model, it will looks ok, but my computer runs too slowly on the 8b CPU.
And The API of Baidu Qianfan is very unstable, possibly because it is a free interface made by a Chinese company. I used this when I started testing, but recently it has been frequently denied access, so I switched to local deployment. However, the performance of my laptop is not very good.
