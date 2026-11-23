pragma solidity 0.8.24;

import {ClientVaultV2} from "../src/ClientVaultV2.sol";
import {StrategyRegistryV2} from "../src/StrategyRegistryV2.sol";
import {VaultFactory} from "../src/VaultFactory.sol";
import {ProxyAdmin} from "@openzeppelin-4/contracts/proxy/transparent/ProxyAdmin.sol";
import {ITransparentUpgradeableProxy} from "@openzeppelin-4/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

interface Vm { function startBroadcast() external; function stopBroadcast() external; }

contract Upgrade {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run(address admin, address registry, address factory, address[] memory vaults) external {
        for (uint256 index = 1; index < vaults.length; ++index) require(vaults[index - 1] < vaults[index]);
        vm.startBroadcast();
        ClientVaultV2 vaultImplementation = new ClientVaultV2();
        StrategyRegistryV2 registryImplementation = new StrategyRegistryV2();
        // Switch the registry and factory first, then process vaults in address order. The owner migration follows the upgrade batch.
        ProxyAdmin(admin).upgrade(ITransparentUpgradeableProxy(registry), address(registryImplementation));
        VaultFactory(factory).setVaultImplementation(address(vaultImplementation));
        for (uint256 index; index < vaults.length; ++index) {
            ProxyAdmin(admin).upgrade(ITransparentUpgradeableProxy(vaults[index]), address(vaultImplementation));
        }
        for (uint256 index; index < vaults.length; ++index) ClientVaultV2(vaults[index]).migrateFromV1();
        vm.stopBroadcast();
    }
}
