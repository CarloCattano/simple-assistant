import types
import unittest

from utils import auth


class IsAdminTests(unittest.TestCase):
    def _make_update(self, user_id=None):
        update = types.SimpleNamespace()
        if user_id is not None:
            update.effective_user = types.SimpleNamespace(id=user_id)
        else:
            update.effective_user = None
        return update

    def test_is_admin_true_when_ids_match(self):
        auth.ADMIN_ID = "12345"
        update = self._make_update(user_id=12345)

        self.assertTrue(auth.is_admin(update))

    def test_is_admin_false_when_ids_do_not_match(self):
        auth.ADMIN_ID = "12345"
        update = self._make_update(user_id=67890)

        self.assertFalse(auth.is_admin(update))

    def test_is_admin_false_when_no_user(self):
        auth.ADMIN_ID = "12345"
        update = self._make_update(user_id=None)

        self.assertFalse(auth.is_admin(update))


if __name__ == "__main__":
    unittest.main()
