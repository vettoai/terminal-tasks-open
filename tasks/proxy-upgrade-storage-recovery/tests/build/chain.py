import gzip
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from web3 import Web3

CHAIN = 11155111
IMPL_SLOT = int.from_bytes(Web3.keccak(text="eip1967.proxy.implementation"), "big") - 1
ADMIN_SLOT = int.from_bytes(Web3.keccak(text="eip1967.proxy.admin"), "big") - 1
INIT5 = int("f0c57e16840df040f15088dc2f81fe391c3923bec73e23a9662efc9c229c6a00", 16)
OWNER5 = int("9016d09d72d40fdae2fd8ceac6b6234c7706214fd39c1cd1e609a0528c199300", 16)


def dump(web3, path):
    encoded = web3.provider.make_request("anvil_dumpState", [])
    assert "result" in encoded, encoded
    raw = bytes.fromhex(encoded["result"][2:])
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    state = json.loads(raw)
    Path(path).write_text(json.dumps(state))
    return state


class Node:
    def __init__(self, directory, load=None, launcher=None, port=0):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.socket = self.directory / "rpc.ipc"
        command = ["/usr/local/bin/anvil", "--silent", "--accounts", "0", "--chain-id", str(CHAIN),
                   "--base-fee", "0", "--gas-price", "0", "--timestamp", "1759800000", "--hardfork", "paris",
                   "--port", str(port), "--ipc", str(self.socket), "--prune-history", "--transaction-block-keeper", "1", "--no-request-size-limit"]
        if load:
            command += ["--load-state", str(load)]
        self.log = open(self.directory / "anvil.log", "wb")
        self.process = (launcher or subprocess.Popen)(command, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.web3 = Web3(Web3.IPCProvider(str(self.socket), timeout=15))
        for attempt in range(150):
            if self.process.poll() is not None:
                raise RuntimeError((self.directory / "anvil.log").read_text())
            try:
                if self.web3.eth.chain_id == CHAIN:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            self.close()
            raise RuntimeError("Anvil readiness failed")

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.log.close()


def rpc(web3, method, params):
    reply = web3.provider.make_request(method, params)
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"]


def artifact(project, name):
    return json.loads((Path(project) / "out" / (name + ".sol") / (name + ".json")).read_text())


def contract(web3, project, name, address=None):
    item = artifact(project, name)
    return web3.eth.contract(address=Web3.to_checksum_address(address) if address else None,
                             abi=item["abi"], bytecode=item["bytecode"]["object"])


def send(web3, key, target=None, data="0x", timestamp=None):
    sender = Account.from_key(key).address
    transaction = dict(chainId=CHAIN, nonce=web3.eth.get_transaction_count(sender), gas=4000000,
                       gasPrice=0, value=0, data=data)
    if target:
        transaction["to"] = Web3.to_checksum_address(target)
    raw = Account.sign_transaction(transaction, key).raw_transaction
    if timestamp is not None:
        rpc(web3, "evm_setNextBlockTimestamp", [timestamp])
    txhash = web3.eth.send_raw_transaction(raw)
    receipt = web3.eth.wait_for_transaction_receipt(txhash, timeout=20, poll_latency=0.01)
    assert receipt["gasUsed"] <= 2000000, receipt
    return "0x" + raw.hex(), receipt


def transact(web3, key, function, expect=1):
    raw, receipt = send(web3, key, function.address, function._encode_transaction_data())
    assert receipt.status == expect, (function.fn_name, receipt)
    return raw, receipt


def deploy(web3, key, project, name, arguments=()):
    factory = contract(web3, project, name)
    raw, receipt = send(web3, key, data=factory.constructor(*arguments).data_in_transaction)
    assert receipt.status == 1, (name, receipt)
    return contract(web3, project, name, receipt.contractAddress), raw, receipt


def word(web3, address, slot, value):
    rpc(web3, "anvil_setStorageAt", [address, hex(slot), "0x" + int(value).to_bytes(32, "big").hex()])


def plain(value):
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def receipt_evidence(receipt):
    receipt = plain(receipt)
    number = lambda value: int(value, 16) if isinstance(value, str) else int(value)
    logs = [(entry["address"].lower(), tuple(topic.lower() for topic in entry["topics"]), entry["data"].lower())
            for entry in receipt["logs"]]
    return number(receipt["status"]), logs, number(receipt["gasUsed"])


def candidate_receipts(web3, row, address, candidates):
    raw = row["raw_transaction"]
    transaction = Transaction.from_bytes(bytes.fromhex(raw[2:]))
    sender = Account.recover_transaction(raw)
    results = {}
    for label, storage in candidates.items():
        snapshot = rpc(web3, "evm_snapshot", [])
        try:
            rpc(web3, "anvil_setNonce", [sender, hex(transaction.nonce)])
            for slot, value in storage.items():
                word(web3, address, slot, value)
            txhash = web3.eth.send_raw_transaction(raw)
            receipt = web3.eth.wait_for_transaction_receipt(txhash, timeout=20, poll_latency=0.01)
            results[label] = receipt_evidence(receipt)
        finally:
            assert rpc(web3, "evm_revert", [snapshot])
    return results


def timestamp_candidates(web3, row, address):
    topic = "0x" + Web3.keccak(text="CompoundConfigUpdated(bool,uint32,bool,uint32)").hex()
    event = next(entry for entry in row["receipt"]["logs"]
                 if entry["address"].lower() == address.lower() and entry["topics"][0].lower() == topic.lower())
    old_enabled, old_cooldown, _, _ = web3.codec.decode(
        ["bool", "uint32", "bool", "uint32"], bytes.fromhex(event["data"][2:]))
    upper = int.from_bytes(web3.eth.get_storage_at(address, 102), "big") & ~((1 << 40) - 1)
    base = upper | old_cooldown << 8
    candidates = {low: {102: base | low} for low in range(256)}
    executions = candidate_receipts(web3, row, address, candidates)
    expected = receipt_evidence(row["receipt"])
    matching = [low for low, evidence in executions.items() if evidence == expected]
    assert matching and all(bool(low) == old_enabled for low in matching)
    return base, matching, executions
