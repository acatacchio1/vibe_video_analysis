import logging
import json
import time
import requests

logger = logging.getLogger(__name__)


def patch_reasoning_content():
    from video_analyzer.clients.generic_openai_api import GenericOpenAIAPIClient

    def wrapped_generate(
        self,
        prompt,
        image_path=None,
        stream=False,
        model="llama3.2-vision",
        temperature=0.2,
        num_predict=256,
    ):
        if image_path:
            b64 = self.encode_image(image_path)
            content_list = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]
        else:
            content_list = prompt

        data = {
            "model": model,
            "messages": [{"role": "user", "content": content_list}],
            "stream": stream,
            "temperature": temperature,
            "max_tokens": num_predict,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries):
            try:
                resp = requests.post(self.generate_url, headers=headers, json=data)
                resp.raise_for_status()
                jr = resp.json()
                if "error" in jr:
                    raise Exception(f"API error: {jr['error']}")
                if "choices" not in jr or not jr["choices"]:
                    raise Exception("No choices")
                msg = jr["choices"][0].get("message", {})
                c = msg.get("content")
                if c is None:
                    rc = msg.get("reasoning_content")
                    if rc:
                        c = rc
                        logger.info("Used reasoning_content as content (model returns null content)")
                if c is None:
                    raise Exception("No content or reasoning content in response")
                if stream:
                    return self._handle_streaming_response(resp)
                return {"response": c}
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise Exception(f"An error occurred: {str(e)}")
                w = 25
                if isinstance(e, requests.exceptions.HTTPError) and getattr(e, "response", None) and e.response.status_code == 429:
                    ra = e.response.headers.get("Retry-After")
                    if ra:
                        try:
                            w = int(ra)
                        except ValueError:
                            pass
                logger.warning("Retry %d/%d: %s, wait %ds", attempt + 1, self.max_retries, e, w)
                time.sleep(w)

    GenericOpenAIAPIClient.generate = wrapped_generate
    logger.info("Applied reasoning_content patch to GenericOpenAIAPIClient")
