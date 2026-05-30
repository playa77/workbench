import unittest

from worker_plan_internal.llm_util.token_counter import extract_token_count


class TestTokenCounter(unittest.TestCase):
    def test_top_level_token_fields_keep_usage_like_raw_data_only(self):
        response = {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
            "model": "gpt-4.1",
            "content": "large payload that should not be stored in raw_usage_data",
            "messages": [{"role": "assistant", "content": "hello"}],
        }

        token_count = extract_token_count(response)

        self.assertEqual(token_count.input_tokens, 10)
        self.assertEqual(token_count.output_tokens, 4)
        self.assertEqual(token_count.thinking_tokens, None)
        self.assertEqual(
            token_count.raw_usage_data,
            {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            },
        )

    def test_nested_usage_path_is_unchanged(self):
        response = {
            "usage": {
                "input_tokens": 3,
                "output_tokens": 2,
                "provider_metric": "keep-this",
            }
        }

        token_count = extract_token_count(response)

        self.assertEqual(token_count.input_tokens, 3)
        self.assertEqual(token_count.output_tokens, 2)
        self.assertEqual(
            token_count.raw_usage_data,
            {
                "input_tokens": 3,
                "output_tokens": 2,
                "provider_metric": "keep-this",
            },
        )


if __name__ == "__main__":
    unittest.main()
