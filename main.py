import os
import json
import requests
import redis
from google.cloud import pubsub_v1
from llama_cpp import Llama

class RecipeGenerator:
    def __init__(self, model_path="./model.gguf"):
        if not os.path.exists(model_path):
             model_path = "./model.gguf" 
             
        # n_ctx aumentado para 1024 pois receitas podem ser maiores que piadas
        self.llm = Llama(model_path=model_path, n_ctx=1024, verbose=False)

    def generate_text(self, topic):
        # PROMPT DE SISTEMA ALTERADO PARA CONTEXTO CULINÁRIO
        prompt = f"""<|im_start|>system
You are an experienced Chef. Your goal is to suggest a delicious recipe based on the user's request.
Provide the ingredients list and short preparation steps. Keep it concise but tasty.<|im_end|>
<|im_start|>user
Write a recipe for: {topic}<|im_end|>
<|im_start|>assistant
"""
        try:
            print(f"Generating recipe for: {topic}")
            output = self.llm.create_completion(
                prompt, 
                max_tokens=256,   # Aumentado para permitir texto maior
                temperature=0.7,  # Ligeiramente mais criativo
                repeat_penalty=1.1,
                stop=["<|im_end|>", "<|endoftext|>"]
            )
            return output['choices'][0]['text'].strip()
        except Exception as e:
            print(f"Error generation: {e}")
            return "Error generating recipe"

def send_to_discord(webhook_url, content):
    try:
        # Formata a mensagem para ficar bonita no Discord
        formatted_content = f"**🍽️ Receita Pronta!**\n\n{content}"
        data = {"content": formatted_content}
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
        print(f"Sent to Discord: {response.status_code}")
    except Exception as e:
        print(f"Error sending to Discord: {e}")

def callback(message):
    print(f"Received message: {message.data}")
    
    try:
        data = json.loads(message.data.decode('utf-8'))
        instruction = data.get('instruction', '')
        
        print(f"Processing recipe for: {instruction}")
        
        # Cache no Redis (Chave: ingrediente -> Valor: receita)
        cached_recipe = redis_client.get(instruction)
        
        if cached_recipe:
            recipe_text = cached_recipe.decode('utf-8')
            print("Using cached recipe from Redis")
        else:
            recipe_text = generator.generate_text(instruction)
            # Guarda no Redis com expiração de 24h (opcional, mas boa prática)
            redis_client.setex(instruction, 86400, recipe_text)
            print("Generated new recipe")
        
        webhook_url = os.environ.get('DISCORD_URL')
        if webhook_url:
            send_to_discord(webhook_url, recipe_text)
        else:
            print("Warning: DISCORD_URL not set")
        
        message.ack()
        
    except Exception as e:
        print(f"Error processing message: {e}")
        message.nack()

def main():
    global redis_client
    
    redis_host = os.environ.get('REDIS_HOST')
    redis_port = int(os.environ.get('REDIS_PORT', 6379))
    redis_auth_string = os.environ.get('REDIS_AUTH_STRING')

    print(f"Connecting to Redis at {redis_host}:{redis_port}...")
    
    redis_client = redis.Redis(
        host=redis_host, 
        port=redis_port, 
        password=redis_auth_string, 
        decode_responses=False,
        socket_connect_timeout=5,
        retry_on_timeout=True
    )
    
    project_id = os.environ.get('GCP_PROJECT_ID')
    subscription_id = os.environ.get('PUBSUB_SUBSCRIPTION_ID')
    
    if not project_id or not subscription_id:
        print("Error: GCP_PROJECT_ID and PUBSUB_SUBSCRIPTION_ID must be set")
        return
    
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(project_id, subscription_id)
    
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    print(f"Listening for recipes on: {subscription_path}...")
    
    try:
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()

# Inicializa o Gerador
generator = RecipeGenerator()

if __name__ == "__main__":
    main()