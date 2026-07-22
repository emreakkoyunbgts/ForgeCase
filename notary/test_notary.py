import os
import unittest
from notary.notary import append_to_log, get_last_hash, print_chain, LOG_FILE

class TestNotaryModule(unittest.TestCase):

    def setUp(self):
        """
        Clears the log file before ech test run
        """
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)

    def tear_down(self):
        """
        Clears down everything after tests are done
        """
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)

    def test_01_empty_file_genesis_hash(self):
        """
        Edge Case 1: When the File is empty/unexisted Genesis (64 0's) should return hash
        """
        self.assertEqual(get_last_hash(), "0" * 64)

    def test_02_hash_chaining(self):
        """
        Normal Flow: The datas that comes one by one should be linked together
        """
        h1 = append_to_log("First Load to System")
        h2 = append_to_log("User Logged In to the System")

        self.assertNotEqual(h1, h2)
        self.assertEqual(get_last_hash(), h2)

    def test_03_special_characters_and_pipe(self):
        """
        Edge Case 2: If there is a '|' (pipe) symbol or Turkish characters in the data the system should not
        crash
        """
        complex_data = "User | Role: Admin | Operation: Deletion | Detail: A&B_123"
        h = append_to_log(complex_data)

        self.assertEqual(get_last_hash(), h)

    def test_04_print_chain_executes_without_error(self):
        """
        Normal Flow: print_chain function should print to the screen without an error
        """

        append_to_log("Test Data 1")
        append_to_log("Test Data 2")

        try:
            print_chain()
            success = True
        except Exception:
            success = False
        
        self.assertTrue(success)

if __name__ == "__main__":
    unittest.main()