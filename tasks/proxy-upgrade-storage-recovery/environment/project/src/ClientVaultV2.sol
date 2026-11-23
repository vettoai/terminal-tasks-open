pragma solidity 0.8.24;

import {Initializable} from "@openzeppelin-5/contracts-upgradeable/proxy/utils/Initializable.sol";
import {OwnableUpgradeable} from "@openzeppelin-5/contracts-upgradeable/access/OwnableUpgradeable.sol";

contract ClientVaultV2 is Initializable, OwnableUpgradeable {
    struct RewardSwapConfig {
        bool enabled;
        address tokenIn;
        address tokenOut;
        uint24 fee;
        uint160 sqrtPriceLimitX96;
    }

    uint256[100] private __legacyGap;
    bool public automationEnabled;
    bool public paused;
    uint32 public cooldownSec;
    uint16 public maxSlippageBps;
    bool public allowSwap;
    bool public dailyHarvestEnabled;
    uint32 public dailyHarvestCooldownSec;
    uint256 public lastDailyHarvestTs;
    bool public compoundEnabled;
    uint32 public compoundCooldownSec;
    uint256 public lastCompoundTs;
    RewardSwapConfig public rewardSwap;
    uint256 public positionTokenId;
    uint256 public lastRebalanceTs;
    uint256 public strategyId;

    event AutomationToggled(bool enabled);
    event AutomationConfigUpdated(uint32 cooldownSec, uint16 maxSlippageBps, bool allowSwap);
    event DailyHarvestConfigUpdated(bool oldEnabled, uint32 oldCooldownSec, bool enabled, uint32 cooldownSec);
    event CompoundConfigUpdated(bool oldEnabled, uint32 oldCooldownSec, bool enabled, uint32 cooldownSec);
    event RewardSwapConfigUpdated(bool enabled, address tokenIn, address tokenOut, uint24 fee, uint160 sqrtPriceLimitX96);

    constructor() { _disableInitializers(); }

    function initialize(address beneficiary, uint32 cooldown, uint16 slippage, bool swap) public initializer {
        require(beneficiary != address(0));
        __Ownable_init(beneficiary);
        cooldownSec = cooldown;
        maxSlippageBps = slippage;
        allowSwap = swap;
    }

    function migrateFromV1() external reinitializer(2) {
        address beneficiary;
        assembly { beneficiary := sload(51) }
        require(beneficiary != address(0));
        _transferOwnership(beneficiary);
        assembly { sstore(0, 0) sstore(51, 0) }
    }

    function setAutomationEnabled(bool enabled) external onlyOwner {
        automationEnabled = enabled;
        emit AutomationToggled(enabled);
    }

    function setAutomationConfig(uint32 cooldown, uint16 slippage, bool swap) external onlyOwner {
        cooldownSec = cooldown;
        maxSlippageBps = slippage;
        allowSwap = swap;
        emit AutomationConfigUpdated(cooldown, slippage, swap);
    }

    // Configuration changes leave the last execution time in place.
    function setDailyHarvestConfig(bool enabled, uint32 cooldown) external onlyOwner {
        emit DailyHarvestConfigUpdated(dailyHarvestEnabled, dailyHarvestCooldownSec, enabled, cooldown);
        dailyHarvestEnabled = enabled;
        dailyHarvestCooldownSec = cooldown;
    }

    function setCompoundConfig(bool enabled, uint32 cooldown) external onlyOwner {
        emit CompoundConfigUpdated(compoundEnabled, compoundCooldownSec, enabled, cooldown);
        compoundEnabled = enabled;
        compoundCooldownSec = cooldown;
    }

    function setRewardSwapConfig(bool enabled, address tokenIn, address tokenOut, uint24 fee, uint160 priceLimit) external onlyOwner {
        rewardSwap = RewardSwapConfig(enabled, tokenIn, tokenOut, fee, priceLimit);
        emit RewardSwapConfigUpdated(enabled, tokenIn, tokenOut, fee, priceLimit);
    }

    function setStrategyId(uint256 selected) external {
        require(strategyId == 0 && selected != 0);
        strategyId = selected;
    }
}
