
// 0x0818 (0x00a0 - 0x08b8) CastFlags 0x0
class UPalCharacterParameterComponent : public UActorComponent
{
public:
	bool                                               bIsCooping;                    // 0x00a0 (0x0001) [0x0018001040022a21] BoolProperty
	bool                                               bIsEnableSendReticleTarget;    // 0x00a1 (0x0001) [0x0018001040022a21] BoolProperty
	bool                                               bIsEnableMuteki;               // 0x00a2 (0x0001) [0x0018001040022a21] BoolProperty
	bool                                               bIsDisableSummonWeapon;        // 0x00a3 (0x0001) [0x0018001040022a21] BoolProperty
	uint8_t                                            Pad_0000[0x4];                // 0x00a4 (0x0004) MISSED OFFSET
	struct FFixedPoint64                               LeanBackPoint;                 // 0x00a8 (0x0008) [0x0010001000020005] StructProperty
	struct FFixedPoint64                               LeanBackMaxPoint;              // 0x00b0 (0x0008) [0x0010001000020015] StructProperty
	struct FFixedPoint64                               StunPoint;                     // 0x00b8 (0x0008) [0x0010001000020005] StructProperty
	struct FFixedPoint64                               StunMaxPoint;                  // 0x00c0 (0x0008) [0x0010001000020015] StructProperty
	bool                                               bIsInfinitySP;                 // 0x00c8 (0x0001) [0x0018001040000215] BoolProperty
	bool                                               IsSPOverheat;                  // 0x00c9 (0x0001) [0x0018001040000205] BoolProperty
	bool                                               bIsHyperArmor;                 // 0x00ca (0x0001) [0x0018001040000205] BoolProperty
	bool                                               bIsDebugMuteki;                // 0x00cb (0x0001) [0x0018001040000205] BoolProperty
	bool                                               bIsDebugScarecrow;             // 0x00cc (0x0001) [0x0018001040000205] BoolProperty
	uint8_t                                            Pad_0001[0x3];                // 0x00cd (0x0003) MISSED OFFSET
	int32_t                                            DebugScarecrow_Level;          // 0x00d0 (0x0004) [0x0018001040000205] IntProperty
	int32_t                                            DebugScarecrow_Defense;        // 0x00d4 (0x0004) [0x0018001040000205] IntProperty
	EPalElementType                                    ElementType1;                  // 0x00d8 (0x0001) [0x0018001040022a05] EnumProperty
	EPalElementType                                    ElementType2;                  // 0x00d9 (0x0001) [0x0018001040022a05] EnumProperty
	bool                                               IsOverrideTarget;              // 0x00da (0x0001) [0x0018001040012205] BoolProperty
	uint8_t                                            Pad_0002[0x5];                // 0x00db (0x0005) MISSED OFFSET
	struct FVector                                     OverrideTargetLocation;        // 0x00e0 (0x0018) [0x0018001040012225] StructProperty
	bool                                               bIsOverrideDefenceTarget;      // 0x00f8 (0x0001) [0x0018001040012205] BoolProperty
	uint8_t                                            Pad_0003[0x7];                // 0x00f9 (0x0007) MISSED OFFSET
	struct FVector                                     OverrideDefenceTargetLocation; // 0x0100 (0x0018) [0x0018001040012205] StructProperty
	struct FVector                                     OtomoLastActiveLocation;       // 0x0118 (0x0018) [0x0018001040012225] StructProperty
	struct FVector                                     PlayerLastPreFTLocation;       // 0x0130 (0x0018) [0x0018001040012225] StructProperty
	class APalCharacter*                               Trainer;                       // 0x0148 (0x0008) [0x0018001100022a25] ObjectProperty
	TWeakObjectPtr<class APalCharacter>                NPCSpawnedOtomoTrainer;        // 0x0150 (0x0008) [0x001c001040002200] WeakObjectProperty
	bool                                               bIsOtomoStandbyAI;             // 0x0158 (0x0001) [0x0018001040022a35] BoolProperty
	uint8_t                                            Pad_0004[0x7];                // 0x0159 (0x0007) MISSED OFFSET
	class APalCharacter*                               OtomoPal;                      // 0x0160 (0x0008) [0x0018001000022a05] ObjectProperty
	TWeakObjectPtr<class AActor>                       ReticleTargetActor;            // 0x0168 (0x0008) [0x001c001040022a05] WeakObjectProperty
	class UPalIndividualCharacterHandle*               IndividualHandle;              // 0x0170 (0x0008) [0x0018001000022a15] ObjectProperty
	class UPalIndividualCharacterParameter*            IndividualParameter;           // 0x0178 (0x0008) [0x001a00110008023d] ObjectProperty
	bool                                               IsStun;                        // 0x0180 (0x0001) [0x0018001040012205] BoolProperty
	bool                                               IsEnableSpeedCollision;        // 0x0181 (0x0001) [0x0018001040022a01] BoolProperty
	bool                                               IsCanSneakAttacked;            // 0x0182 (0x0001) [0x0018001040022a25] BoolProperty
	bool                                               IsFriendBulletIgnore;          // 0x0183 (0x0001) [0x0018001040002224] BoolProperty
	int32_t                                            BiologicalGrade;               // 0x0184 (0x0004) [0x0018001040022a15] IntProperty
	bool                                               IsPredator;                    // 0x0188 (0x0001) [0x0018001040022a15] BoolProperty
	bool                                               IsEdible;                      // 0x0189 (0x0001) [0x0018001040022a15] BoolProperty
	uint8_t                                            Pad_0005[0x56];                // 0x018a (0x0056) MISSED OFFSET
	EPalElementType                                    DamageUpElement_ByElementStatus; // 0x01e0 (0x0001) [0x0018001040002204] EnumProperty
	EPalElementType                                    DamageDownElement_ByElementStatus; // 0x01e1 (0x0001) [0x0018001040002204] EnumProperty
	bool                                               IsDarknessRandomAttack;        // 0x01e2 (0x0001) [0x0018001040002204] BoolProperty
	uint8_t                                            Pad_0006[0x1];                // 0x01e3 (0x0001) MISSED OFFSET
	int32_t                                            AttackUp;                      // 0x01e4 (0x0004) [0x0018001040002204] IntProperty
	int32_t                                            AttackDown;                    // 0x01e8 (0x0004) [0x0018001040002204] IntProperty
	int32_t                                            DefenseUp;                     // 0x01ec (0x0004) [0x0018001040002204] IntProperty
	TMap<EPalAdditionalEffectType, struct FPalStatusAccumulate> StatusAccumulateMap;           // 0x01f0 (0x0050) [0x0010000000002000] MapProperty
	bool                                               IsSleepAction;                 // 0x0240 (0x0001) [0x0018001040002204] BoolProperty
	uint8_t                                            Pad_0007[0x7];                // 0x0241 (0x0007) MISSED OFFSET
	struct FVector                                     WildPalDrinkWaterPoint;        // 0x0248 (0x0018) [0x0018001040002214] StructProperty
	bool                                               IsDisableOtomoReturnEffect;    // 0x0260 (0x0001) [0x0018001040002204] BoolProperty
	bool                                               IsPendingMeatCutDeath;         // 0x0261 (0x0001) [0x0018001040002204] BoolProperty
	uint8_t                                            Pad_0008[0x2];                // 0x0262 (0x0002) MISSED OFFSET
	float                                              MaxHPRate_ForTowerBoss;        // 0x0264 (0x0004) [0x0018001040002224] FloatProperty
	float                                              AdditionalEnemyMaxHPRate;      // 0x0268 (0x0004) [0x0018001040002224] FloatProperty
	float                                              AdditionalEnemyReceiveDamageRate; // 0x026c (0x0004) [0x0018001040002224] FloatProperty
	float                                              AdditionalEnemyInflictDamageRate; // 0x0270 (0x0004) [0x0018001040002224] FloatProperty
	float                                              MaxSPBuffRate;                 // 0x0274 (0x0004) [0x0018001040002204] FloatProperty
	bool                                               bIsPreCooping;                 // 0x0278 (0x0001) [0x0018001040002204] BoolProperty
	bool                                               bRespawnedWaitTeleport;        // 0x0279 (0x0001) [0x0018001040002214] BoolProperty
	uint8_t                                            Pad_0009[0x6];                // 0x027a (0x0006) MISSED OFFSET
	struct FHitResult                                  GroundHitResult;               // 0x0280 (0x00e8) [0x0020089040022815] StructProperty
	struct FHitResult                                  ClimbSurfaceHitResult;         // 0x0368 (0x00e8) [0x0020089040022801] StructProperty
	uint8_t                                            Pad_000A[0xd];                // 0x0450 (0x000d) MISSED OFFSET
	bool                                               bIsUseGroundRayCast;           // 0x045d (0x0001) [0x0048001040010201] BoolProperty
	uint8_t                                            Pad_000B[0x2];                // 0x045e (0x0002) MISSED OFFSET
	struct FFlagContainer                              DisableGroundRayCast;          // 0x0460 (0x0050) [0x0040000000002000] StructProperty
	struct FFixedPoint64                               SP;                            // 0x04b0 (0x0008) [0x0040001000002000] StructProperty
	struct FGUID                                       BaseCampDefenseModelId;        // 0x04b8 (0x0010) [0x0018001040022a15] StructProperty
	EPalMapBaseCampWorkerOrderType                     BaseCampWorkerOrderType;       // 0x04c8 (0x0001) [0x0018001040022a05] EnumProperty
	bool                                               bBaseCampWorkerAttackableFriend; // 0x04c9 (0x0001) [0x0018001040002201] BoolProperty
	uint8_t                                            Pad_000C[0x6];                // 0x04ca (0x0006) MISSED OFFSET
	TMap<struct FGUID, struct FPalMapObjectAppearanceData> UnreachableMapObjectInfos;     // 0x04d0 (0x0050) [0x0010000000002000] MapProperty
	bool                                               bBeingSleptOnSide;             // 0x0520 (0x0001) [0x0018001040002234] BoolProperty
	uint8_t                                            Pad_000D[0x7];                // 0x0521 (0x0007) MISSED OFFSET
	struct FPalCharacterParameter_Work                 Work;                          // 0x0528 (0x0088) [0x0010000000022801] StructProperty
	struct FPalWorkAssignHandleId                      WorkAssignId;                  // 0x05b0 (0x0018) [0x0018001000022821] StructProperty
	EPalWorkType                                       WorkType;                      // 0x05c8 (0x0001) [0x0018001040022a21] EnumProperty
	uint8_t                                            Pad_000E[0x3];                // 0x05c9 (0x0003) MISSED OFFSET
	struct FGUID                                       BaseCampWalkAroundExcludeMapObjectInstanceId; // 0x05cc (0x0010) [0x0018001040022a01] StructProperty
	bool                                               bAppliedBaseCampWorkerInitialized; // 0x05dc (0x0001) [0x0018001040022a01] BoolProperty
	EPalWorkWorkerWorkingState                         WorkingState;                  // 0x05dd (0x0001) [0x0048001040022a21] EnumProperty
	uint8_t                                            Pad_000F[0x2];                // 0x05de (0x0002) MISSED OFFSET
	struct FName                                       PossessStaticItemId;           // 0x05e0 (0x0008) [0x0018001140022a35] NameProperty
	bool                                               bBeingRescued;                 // 0x05e8 (0x0001) [0x0018001040022a25] BoolProperty
	uint8_t                                            Pad_0010[0x3];                // 0x05e9 (0x0003) MISSED OFFSET
	float                                              DyingHP;                       // 0x05ec (0x0004) [0x0018001040022a25] FloatProperty
	float                                              DyingMaxHP;                    // 0x05f0 (0x0004) [0x0018001040010235] FloatProperty
	uint8_t                                            Pad_0011[0x4];                // 0x05f4 (0x0004) MISSED OFFSET
	class UPalItemContainer*                           ItemContainer;                 // 0x05f8 (0x0008) [0x0048001100022a21] ObjectProperty
	bool                                               IsCapturedProcessing;          // 0x0600 (0x0001) [0x0048001140022a21] BoolProperty
	bool                                               PlayerLastPreFTLocationOverriding; // 0x0601 (0x0001) [0x0048001040002220] BoolProperty
	uint8_t                                            Pad_0012[0xe];                // 0x0602 (0x000e) MISSED OFFSET
	struct FMulticastScriptDelegate                    OnUpdatePossessItemDelegate;   // 0x0610 (0x0010) [0x0010000010080200] MulticastInlineDelegateProperty
	struct FMulticastScriptDelegate                    OnUpdateWorkAssignIdDelegate;  // 0x0620 (0x0010) [0x0010000010080200] MulticastInlineDelegateProperty
	struct FMulticastScriptDelegate                    OnChangeCapturedProcessingDelegate; // 0x0630 (0x0010) [0x0010000010080200] MulticastInlineDelegateProperty
	struct FMulticastScriptDelegate                    OnSPOverheatDelegate;          // 0x0640 (0x0010) [0x0010000010080200] MulticastInlineDelegateProperty
	struct FMulticastScriptDelegate                    OnChangeTrapLegHoldDelegate;   // 0x0650 (0x0010) [0x0010000010080200] MulticastInlineDelegateProperty
	struct FMulticastScriptDelegate                    OnChangeTrapMovingPanelDelegate; // 0x0660 (0x0010) [0x0010000010080200] MulticastInlineDelegateProperty
	struct FVector                                     TrapDirection;                 // 0x0670 (0x0018) [0x0018001040002204] StructProperty
	TMap<struct FPalInstanceID, int32_t>               DamageMap;                     // 0x0688 (0x0050) [0x0010000000002014] MapProperty
	bool                                               CanDropItem;                   // 0x06d8 (0x0001) [0x0018001040002204] BoolProperty
	uint8_t                                            Pad_0013[0x7];                // 0x06d9 (0x0007) MISSED OFFSET
	struct FFlagContainer                              DisableNaturalHealing_Component; // 0x06e0 (0x0050) [0x0010000000002000] StructProperty
	bool                                               IsImmortality;                 // 0x0730 (0x0001) [0x0018001040000224] BoolProperty
	bool                                               IsMimicryMode;                 // 0x0731 (0x0001) [0x0018001040000204] BoolProperty
	bool                                               bIsAttackNonCriminal;          // 0x0732 (0x0001) [0x0018001040000204] BoolProperty
	uint8_t                                            Pad_0014[0x14d];                // 0x0733 (0x014d) MISSED OFFSET
	TArray<TWeakObjectPtr<class AActor>>               TrapLegHoldList;               // 0x0880 (0x0010) [0x0024080000002200] ArrayProperty
	TArray<TWeakObjectPtr<class AActor>>               TrapMovingPanelList;           // 0x0890 (0x0010) [0x0024080000002200] ArrayProperty
	class UPalOtomoAttackStopJudgeByBallList*          OtomoAttackStopJudge;          // 0x08a0 (0x0008) [0x0028081000002200] ObjectProperty
	TArray<struct FPalMapObjectAppearanceDataWithId>   UnreachableMapObjectRepInfoArray; // 0x08a8 (0x0010) [0x0010000000002220] ArrayProperty

public:
	// void AddDyingHP(float AddHP);  // flags 0x04020401  native 0x20d08b0
	// void AddHP(struct FFixedPoint64 PlusHP);  // flags 0x04020401  native 0x20d0950
	// void AddHP_ToServer(struct FFixedPoint64 AddHP);  // flags 0x00240cc1  native 0x20ce120
	// void AddHPByRate(float Rate);  // flags 0x04020401  native 0x20d09f0
	// void AddHPByRate_ToServer(float Rate);  // flags 0x00240cc1  native 0x20ce080
	// void AddTrapLegHold(class AActor* TrapActor);  // flags 0x04020401  native 0x20cebd0
	// void AddTrapMovingPanel(class AActor* TrapActor);  // flags 0x04020401  native 0x20cea60
	// bool CanTargetFromAI();  // flags 0x54020401  native 0x20d0c50
	// struct FGUID GetBaseCampID();  // flags 0x54820401  native 0x20cf130
	// float GetCapsuleRadius();  // flags 0x54020401  native 0x20d0ed0
	// int32_t GetCraftSpeed();  // flags 0x14020401  native 0x20d05d0
	// int32_t GetCraftSpeed_WorkSuitability(EPalWorkSuitability WorkSuitability);  // flags 0x14020401  native 0x20d0520
	// int32_t GetDefense();  // flags 0x14020401  native 0x20d0600
	// class UPrimitiveComponent* GetFloorComponent();  // flags 0x40020401  native 0x20d0e70
	// struct FVector GetFloorLocation();  // flags 0x54820401  native 0x20d0ea0
	// EPhysicalSurface GetFloorPhisicalSurface();  // flags 0x54020401  native 0x20cf0d0
	// float GetFullStomach();  // flags 0x14020401  native 0x20d06f0
	// struct FHitResult GetHitGroundResult();  // flags 0x54020401  native 0x20cf2e0
	// struct FFixedPoint64 GetHp();  // flags 0x54020401  native 0x20d0ac0
	// float GetHPRate();  // flags 0x14020401  native 0x20d0a90
	// class UPalIndividualCharacterParameter* GetIndividualParameter();  // flags 0x54020401  native 0x20d0dd0
	// bool GetIsCapturedProcessing();  // flags 0x14020401  native 0x20cf190
	// int32_t GetLegHoldResistLevel();  // flags 0x14020401  native 0x20ceb00
	// int32_t GetLevel();  // flags 0x14020401  native 0x20d0c20
	// struct FGUID GetMapObjectInstanceIdApproachTo();  // flags 0x54820401  native 0x20cf370
	// float GetMaxFullStomach();  // flags 0x14020401  native 0x20d0720
	// struct FFixedPoint64 GetMaxHP();  // flags 0x14020401  native 0x20d0bc0
	// struct FFixedPoint64 GetMaxMP();  // flags 0x14020401  native 0x20d00e0
	// float GetMaxSanity();  // flags 0x14020401  native 0x20d0690
	// struct FFixedPoint64 GetMaxSP();  // flags 0x14020401  native 0x20cfec0
	// int32_t GetMeleeAttack();  // flags 0x14020401  native 0x20d0660
	// struct FFixedPoint64 GetMP();  // flags 0x14020401  native 0x20d01e0
	// void GetNickName(class FString* outName);  // flags 0x14420401  native 0x20d0460
	// void GetNickNamebyByCheckBlockedUser(class FString* outName);  // flags 0x14420401  native 0x20d03a0
	// void GetNickNameWithOnlineId(class FString* outName);  // flags 0x14420401  native 0x20d02e0
	// class UPalOtomoAttackStopJudgeByBallList* GetOtomoAttackStopJudge();  // flags 0x14020401  native 0x20cf160
	// struct FVector GetOtomoLastActiveLocation();  // flags 0x54820401  native 0x20cf9b0
	// struct FVector GetOverrideDefenceTargetLocation();  // flags 0x54820401  native 0x20cfb00
	// struct FVector GetOverrideTargetLocation_ConsiderRide();  // flags 0x14820401  native 0x20cf270
	// struct FVector GetPlayerLastPreFTLocation();  // flags 0x54820401  native 0x20cf890
	// float GetRadius();  // flags 0x54020401  native 0x20d0f00
	// class AActor* GetReticleTargetActor();  // flags 0x04020401  native 0x20cf810
	// float GetSanity();  // flags 0x14020401  native 0x20d06c0
	// int32_t GetShotAttack();  // flags 0x14020401  native 0x20d0630
	// struct FFixedPoint64 GetSP();  // flags 0x14020401  native 0x20cffe0
	// struct FPalStatusHit GetStatusHit(EPalStatusHitType StatusHitType);  // flags 0x54020401  native 0x20cf600
	// class UPalWorkBase* GetWork();  // flags 0x54020401  native 0x20cf400
	// class UPalWorkAssign* GetWorkAssign();  // flags 0x54020401  native 0x20cf460
	// struct FGUID GetWorkId();  // flags 0x54820401  native 0x20cf430
	// bool HasElementType(EPalElementType ElementType);  // flags 0x54020401  native 0x20cf490
	// bool HasFloorPhysMaterial();  // flags 0x54020401  native 0x20cf100
	// bool IsAssignedFixed();  // flags 0x54020401  native 0x20cf3a0
	// bool IsAssignedToAnyWork();  // flags 0x54020401  native 0x20cf3d0
	// bool IsCooping();  // flags 0x54020401  native 0x20cfde0
	// bool IsDead();  // flags 0x54020401  native 0x20d0d20
	// bool IsDisableSummonWeapon();  // flags 0x54020401  native 0x20ced70
	// bool IsDying();  // flags 0x54020401  native 0x20d0cb0
	// bool IsDyingHPMax();  // flags 0x54020401  native 0x20d07c0
	// bool IsDyingHPZero();  // flags 0x54020401  native 0x20d0790
	// bool IsHittingLava();  // flags 0x54020401  native 0x20d0e20
	// bool IsHyperArmor();  // flags 0x54020401  native 0x20cfdb0
	// bool IsInactiveOtomo();  // flags 0x54020401  native 0x20cfad0
	// bool IsInfinitySP();  // flags 0x54020401  native 0x20d0e50
	// bool IsLive();  // flags 0x54020401  native 0x20d0cf0
	// bool IsMuteki();  // flags 0x14020401  native 0x20ceea0
	// bool IsOtomo();  // flags 0x54020401  native 0x20d0da0
	// bool IsOtomoStandbyAI();  // flags 0x54020401  native 0x20d0d50
	// bool IsOverrideDefenceTarget();  // flags 0x54020401  native 0x20cfb70
	// bool IsPartBroken();  // flags 0x54020401  native 0x20d0c80
	// bool IsPlayerLastPreFTLocationValid();  // flags 0x54020401  native 0x20cf860
	// bool IsPlayersOtomo();  // flags 0x54020401  native 0x20d0d70
	// bool IsStatusHitActive(struct FPalStatusHit* StatusHit);  // flags 0x14422401  native 0x20cf540
	// void Multicast_DecreaseAllActiveSkillCoolDownByRate(float Rate);  // flags 0x00024cc0  native 0x20ce350
	// void OnChangeCapturedProcessing__DelegateSignature(bool bIsCapturedProcessing);  // flags 0x00130000  native 0x30854e0
	// void OnChangeTrapDelegate__DelegateSignature(bool IsExist);  // flags 0x00130000  native 0x30854e0
	// void OnDamage(struct FPalDamageResult DamageResult);  // flags 0x00040401  native 0x20ce6f0
	// void OnInitialize_AfterSetIndividualParameter(class APalCharacter* Character);  // flags 0x00040401  native 0x20ce820
	// void OnInitializedCharacter(class APalCharacter* OwnerCharacter);  // flags 0x00040401  native 0x20cdfe0
	// void OnRep_IndividualParameter();  // flags 0x00020401  native 0x20d0f30
	// void OnRep_IsCapturedProcessing();  // flags 0x00040401  native 0x20d0e00
	// void OnRep_ItemContainer();  // flags 0x00080401  native 0x20cdfc0
	// void OnRep_PossessStaticItemId();  // flags 0x00040401  native 0x20ce800
	// void OnRep_Trainer();  // flags 0x00080401  native 0x20cdfa0
	// void OnSlipDamage(struct FPalDamageResult* DamageResult);  // flags 0x00440401  native 0x20ce5f0
	// void RemoveTrapLegHold(class AActor* TrapActor);  // flags 0x04020401  native 0x20ceb30
	// void RemoveTrapMovingPanel(class AActor* TrapActor);  // flags 0x04020401  native 0x20ce9c0
	// void ResetDyingHP();  // flags 0x04020401  native 0x20d0770
	// void ResetOverrideDefenceTarget();  // flags 0x04020401  native 0x20cf840
	// void ResetSP();  // flags 0x04020401  native 0x20cffc0
	// void ReviveFromDying();  // flags 0x04020401  native 0x20d0750
	// void SetCoopingFlag(bool IsEnable);  // flags 0x04020401  native 0x20cfe10
	// void SetDisableCreateUNKO(struct FName flagName, bool isDisable);  // flags 0x04020401  native 0x20cefd0
	// void SetDisableNaturalHealing_Component(struct FName Key, bool Disable);  // flags 0x04020401  native 0x20ce8c0
	// void SetDisableSummonWeapon(struct FName flagName, bool isDisable);  // flags 0x04020401  native 0x20ceda0
	// void SetElementTypeFromDatabase(class APalCharacter* InCharacter);  // flags 0x00020401  native 0x20cf750
	// void SetEnableSendReticleTarget(struct FName flagName, bool IsEnable);  // flags 0x04020401  native 0x20cec70
	// void SetHP(struct FFixedPoint64 NewHP);  // flags 0x04020401  native 0x20d0b20
	// void SetIsCapturedProcessing(bool IsCaptureProcess);  // flags 0x04020401  native 0x20cf1c0
	// void SetIsOverrideTarget(bool IsOverride);  // flags 0x04020401  native 0x20cfd00
	// void SetIsOverrideTarget_Innner(bool IsOverride);  // flags 0x00040401  native 0x20ce2a0
	// void SetIsOverrideTarget_ToALL(int32_t ID, bool IsOverride);  // flags 0x00044cc1  native 0x20ce3f0
	// void SetIsOverrideTarget_ToServer(int32_t ID, bool IsOverride);  // flags 0x00240cc1  native 0x20ce4f0
	// void SetMaxMP(struct FFixedPoint64 NewMaxMP);  // flags 0x04020401  native 0x20d0140
	// void SetMaxSP(struct FFixedPoint64 NewMaxSP);  // flags 0x04020401  native 0x20cff20
	// void SetMP(struct FFixedPoint64 NewMP);  // flags 0x04020401  native 0x20d0240
	// void SetMuteki(struct FName flagName, bool IsEnable);  // flags 0x04020401  native 0x20ceed0
	// void SetOtomoLastActiveLocation(struct FVector* Location);  // flags 0x04c20401  native 0x20cfa20
	// void SetOverrideDefenceTargetLocation(struct FVector TargetLocation);  // flags 0x04820401  native 0x20cfba0
	// void SetOverrideTargetLocation(struct FVector TargetLocation);  // flags 0x04820401  native 0x20cfc50
	// void SetOverrideTargetLocation_ToServer(struct FVector TargetLocation);  // flags 0x00a40c41  native 0x20ce1f0
	// void SetPlayerLastPreFTLocation(struct FVector* Location);  // flags 0x04c20401  native 0x20cf900
	// void SetReticleTarget_ToServer(class AActor* Actor);  // flags 0x00240cc1  native 0x204cc80
	// void SetSP(struct FFixedPoint64 NewSP);  // flags 0x04020401  native 0x20d0040
	// void SetTrainer(class APalCharacter* inTrainer);  // flags 0x04020401  native 0x20cf6b0
	// void SetupBiologicalGradeFromDatabase();  // flags 0x04020401  native 0x20cf7f0
	// void SPOverheatDelegate__DelegateSignature();  // flags 0x00130000  native 0x30854e0
	// void SubDyingHP(float SubHP);  // flags 0x04020401  native 0x20d0810
	// void UpdateParameterDelegate__DelegateSignature(class UPalCharacterParameterComponent* Parameter);  // flags 0x00130000  native 0x30854e0
	// void UpdateWorkAssignIdDelegate__DelegateSignature(class UPalCharacterParameterComponent* Parameter);  // flags 0x00130000  native 0x30854e0
	// void ZeroDyingHP();  // flags 0x04020401  native 0x20d07f0
	// void ZeroDyingHP_ToServer();  // flags 0x00240cc1  native 0x20ce1d0
};


// 0x0370 (0x0000 - 0x0370)
struct FPalIndividualCharacterSaveParameter
{
	struct FName                                       CharacterID;                   // 0x0000 (0x0008) [0x0018001040000205] NameProperty
	struct FName                                       UniqueNPCID;                   // 0x0008 (0x0008) [0x0018001040000201] NameProperty
	EPalGenderType                                     Gender;                        // 0x0010 (0x0001) [0x0018001040000201] EnumProperty
	uint8_t                                            Pad_0000[0x7];                // 0x0011 (0x0007) MISSED OFFSET
	class UClass*                                      CharacterClass;                // 0x0018 (0x0008) [0x001c001000002201] ClassProperty
	uint8_t                                            Level;                         // 0x0020 (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Rank;                          // 0x0021 (0x0001) [0x0018001040000201] ByteProperty
	uint16_t                                           RankUpExp;                     // 0x0022 (0x0002) [0x0018001040000201] UInt16Property
	uint8_t                                            Rank_HP;                       // 0x0024 (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Rank_Attack;                   // 0x0025 (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Rank_Defence;                  // 0x0026 (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Rank_CraftSpeed;               // 0x0027 (0x0001) [0x0018001040000201] ByteProperty
	int64_t                                            Exp;                           // 0x0028 (0x0008) [0x0018001040000201] Int64Property
	class FString                                      NickName;                      // 0x0030 (0x0010) [0x0018000000000201] StrProperty
	class FString                                      FilteredNickName;              // 0x0040 (0x0010) [0x0018000000000201] StrProperty
	bool                                               IsRarePal;                     // 0x0050 (0x0001) [0x0018001040000201] BoolProperty
	bool                                               bIsAwakening;                  // 0x0051 (0x0001) [0x0018001040000201] BoolProperty
	uint8_t                                            Pad_0001[0x6];                // 0x0052 (0x0006) MISSED OFFSET
	TArray<EPalWazaID>                                 EquipWaza;                     // 0x0058 (0x0010) [0x0010000000000201] ArrayProperty
	TArray<EPalWazaID>                                 MasteredWaza;                  // 0x0068 (0x0010) [0x0010000000000201] ArrayProperty
	struct FFixedPoint64                               Hp;                            // 0x0078 (0x0008) [0x0010001000000001] StructProperty
	uint8_t                                            Talent_HP;                     // 0x0080 (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Talent_Melee;                  // 0x0081 (0x0001) [0x0018001040002201] ByteProperty
	uint8_t                                            Talent_Shot;                   // 0x0082 (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Talent_Defense;                // 0x0083 (0x0001) [0x0018001040000201] ByteProperty
	float                                              FullStomach;                   // 0x0084 (0x0004) [0x0018001040000201] FloatProperty
	EPalStatusPhysicalHealthType                       PhysicalHealth;                // 0x0088 (0x0001) [0x0018001040000201] EnumProperty
	EPalBaseCampWorkerSickType                         WorkerSick;                    // 0x0089 (0x0001) [0x0018001040000201] EnumProperty
	uint8_t                                            Pad_0002[0x6];                // 0x008a (0x0006) MISSED OFFSET
	TArray<struct FName>                               PassiveSkillList;              // 0x0090 (0x0010) [0x0010000000000201] ArrayProperty
	int32_t                                            DyingTimer;                    // 0x00a0 (0x0004) [0x0018001040002201] IntProperty
	uint8_t                                            Pad_0003[0x4];                // 0x00a4 (0x0004) MISSED OFFSET
	struct FFixedPoint64                               MP;                            // 0x00a8 (0x0008) [0x0010001000002001] StructProperty
	bool                                               IsPlayer;                      // 0x00b0 (0x0001) [0x0018001040000201] BoolProperty
	uint8_t                                            Pad_0004[0x7];                // 0x00b1 (0x0007) MISSED OFFSET
	struct FDateTime                                   OwnedTime;                     // 0x00b8 (0x0008) [0x0018001000020a01] StructProperty
	struct FGUID                                       OwnerPlayerUId;                // 0x00c0 (0x0010) [0x0018001040020a01] StructProperty
	TArray<struct FGUID>                               OldOwnerPlayerUIds;            // 0x00d0 (0x0010) [0x0010000000020a01] ArrayProperty
	struct FFixedPoint64                               MaxHP;                         // 0x00e0 (0x0008) [0x0010001000002001] StructProperty
	int32_t                                            Support;                       // 0x00e8 (0x0004) [0x0018001040002201] IntProperty
	int32_t                                            CraftSpeed;                    // 0x00ec (0x0004) [0x0018001040002201] IntProperty
	TArray<struct FPalWorkSuitabilityInfo>             CraftSpeeds;                   // 0x00f0 (0x0010) [0x0010000000002201] ArrayProperty
	struct FFixedPoint64                               ShieldHP;                      // 0x0100 (0x0008) [0x0010001000000001] StructProperty
	struct FFixedPoint64                               ShieldMaxHP;                   // 0x0108 (0x0008) [0x0010001000002001] StructProperty
	bool                                               bApplyShieldDamage;            // 0x0110 (0x0001) [0x0018001040000201] BoolProperty
	uint8_t                                            Pad_0005[0x7];                // 0x0111 (0x0007) MISSED OFFSET
	struct FFixedPoint64                               MaxMP;                         // 0x0118 (0x0008) [0x0010001000002001] StructProperty
	struct FFixedPoint64                               MaxSP;                         // 0x0120 (0x0008) [0x0010001000002001] StructProperty
	EPalStatusHungerType                               HungerType;                    // 0x0128 (0x0001) [0x0018001040000201] EnumProperty
	uint8_t                                            Pad_0006[0x3];                // 0x0129 (0x0003) MISSED OFFSET
	float                                              SanityValue;                   // 0x012c (0x0004) [0x0018001040000205] FloatProperty
	EPalBaseCampWorkerEventType                        BaseCampWorkerEventType;       // 0x0130 (0x0001) [0x0018001040000201] EnumProperty
	uint8_t                                            Pad_0007[0x3];                // 0x0131 (0x0003) MISSED OFFSET
	float                                              BaseCampWorkerEventProgressTime; // 0x0134 (0x0004) [0x0018001040000201] FloatProperty
	struct FPalContainerId                             ItemContainerId;               // 0x0138 (0x0010) [0x0018001000000001] StructProperty
	struct FPalContainerId                             EquipItemContainerId;          // 0x0148 (0x0010) [0x0018001000002001] StructProperty
	struct FPalCharacterSlotId                         SlotId;                        // 0x0158 (0x0014) [0x0010001000020801] StructProperty
	float                                              MaxFullStomach;                // 0x016c (0x0004) [0x0018001040002201] FloatProperty
	float                                              FullStomachDecreaseRate_Tribe; // 0x0170 (0x0004) [0x0018001040002200] FloatProperty
	uint16_t                                           UnusedStatusPoint;             // 0x0174 (0x0002) [0x0018001040000201] UInt16Property
	uint8_t                                            Pad_0008[0x2];                // 0x0176 (0x0002) MISSED OFFSET
	TArray<struct FPalGotStatusPoint>                  GotStatusPointList;            // 0x0178 (0x0010) [0x0010000000000201] ArrayProperty
	TArray<struct FPalGotStatusPoint>                  GotExStatusPointList;          // 0x0188 (0x0010) [0x0010000000000201] ArrayProperty
	struct FFloatContainer                             DecreaseFullStomachRates;      // 0x0198 (0x0010) [0x0010000000002000] StructProperty
	struct FFloatContainer                             AffectSanityRates;             // 0x01a8 (0x0010) [0x0010000000002000] StructProperty
	struct FFloatContainer                             CraftSpeedRates;               // 0x01b8 (0x0010) [0x0010000000002000] StructProperty
	struct FVector                                     LastJumpedLocation;            // 0x01c8 (0x0018) [0x0018001040000200] StructProperty
	struct FName                                       FoodWithStatusEffect;          // 0x01e0 (0x0008) [0x0018001040000200] NameProperty
	int32_t                                            Tiemr_FoodWithStatusEffect;    // 0x01e8 (0x0004) [0x0018001040000200] IntProperty
	uint8_t                                            Pad_0009[0x4];                // 0x01ec (0x0004) MISSED OFFSET
	struct FPalFoodRegeneInfo                          FoodRegeneEffectInfo;          // 0x01f0 (0x0020) [0x0010000000000000] StructProperty
	struct FName                                       FoodWithFullStomachKeep;       // 0x0210 (0x0008) [0x0018001040000200] NameProperty
	int32_t                                            Tiemr_FoodWithFullStomachKeep; // 0x0218 (0x0004) [0x0018001040000200] IntProperty
	EPalWorkSuitability                                CurrentWorkSuitability;        // 0x021c (0x0001) [0x0018001040000200] EnumProperty
	uint8_t                                            Pad_000A[0x3];                // 0x021d (0x0003) MISSED OFFSET
	struct FPalWorkSuitabilityPreferenceInfo           WorkSuitabilityOptionInfo;     // 0x0220 (0x0018) [0x0010000000000801] StructProperty
	bool                                               bAppliedDeathPenarty;          // 0x0238 (0x0001) [0x0018001040000200] BoolProperty
	bool                                               bEnablePlayerRespawnInHardcore; // 0x0239 (0x0001) [0x0018001040000200] BoolProperty
	uint8_t                                            Pad_000B[0x2];                // 0x023a (0x0002) MISSED OFFSET
	float                                              PalReviveTimer;                // 0x023c (0x0004) [0x0018001040000200] FloatProperty
	uint8_t                                            VoiceID;                       // 0x0240 (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Pad_000C[0x3];                // 0x0241 (0x0003) MISSED OFFSET
	struct FGUID                                       SkinAppliedCharacterId;        // 0x0244 (0x0010) [0x0018001040000201] StructProperty
	struct FName                                       SkinName;                      // 0x0254 (0x0008) [0x0018001040000201] NameProperty
	bool                                               IsFavoritePal;                 // 0x025c (0x0001) [0x0018001060000200] BoolProperty
	uint8_t                                            FavoriteIndex;                 // 0x025d (0x0001) [0x0018001040000201] ByteProperty
	uint8_t                                            Pad_000D[0x2];                // 0x025e (0x0002) MISSED OFFSET
	struct FGUID                                       MapObjectConcreteInstanceIdAssignedToExpedition; // 0x0260 (0x0010) [0x0018001040000201] StructProperty
	struct FPalArenaCharacterRestoreParameter          ArenaRestoreParameter;         // 0x0270 (0x0058) [0x0010000000000000] StructProperty
	TArray<struct FPalWorkSuitabilityInfo>             GotWorkSuitabilityAddRankList; // 0x02c8 (0x0010) [0x0010000000000200] ArrayProperty
	struct FGUID                                       LastNickNameModifierPlayerUid; // 0x02d8 (0x0010) [0x0018001040000214] StructProperty
	bool                                               bImportedCharacter;            // 0x02e8 (0x0001) [0x0018001040000200] BoolProperty
	uint8_t                                            Pad_000E[0x3];                // 0x02e9 (0x0003) MISSED OFFSET
	int32_t                                            FriendshipPoint;               // 0x02ec (0x0004) [0x0018001040000200] IntProperty
	int32_t                                            FriendshipOtomoSec;            // 0x02f0 (0x0004) [0x0018001040000200] IntProperty
	int32_t                                            FriendshipActiveOtomoSec;      // 0x02f4 (0x0004) [0x0018001040000200] IntProperty
	int32_t                                            FriendshipBasecampSec;         // 0x02f8 (0x0004) [0x0018001040000200] IntProperty
	bool                                               bFavoriteChangedByFriendship;  // 0x02fc (0x0001) [0x0018001040000200] BoolProperty
	uint8_t                                            Pad_000F[0x3];                // 0x02fd (0x0003) MISSED OFFSET
	int32_t                                            ArenaRankPoint;                // 0x0300 (0x0004) [0x0018001040000200] IntProperty
	bool                                               bDisableSaleInPalLost;         // 0x0304 (0x0001) [0x0018001040000200] BoolProperty
	bool                                               bIsExcludedFromTeamMission;    // 0x0305 (0x0001) [0x0018001040000200] BoolProperty
	uint8_t                                            Pad_0010[0x2];                // 0x0306 (0x0002) MISSED OFFSET
	TArray<struct FPalWorkSuitabilityOverflowGrantedInfo> WorkSuitabilityOverflowGrantedRankList; // 0x0308 (0x0010) [0x0010000000000200] ArrayProperty
	struct FDateTime                                   PartnerSkillLastUsedTime;      // 0x0318 (0x0008) [0x0018001000000200] StructProperty
	float                                              PartnerSkillCoolDownTimeMax;   // 0x0320 (0x0004) [0x0018001040000200] FloatProperty
	uint8_t                                            ExpTableMigrationVersion;      // 0x0324 (0x0001) [0x0018001040000200] ByteProperty
	uint8_t                                            Pad_0011[0x3];                // 0x0325 (0x0003) MISSED OFFSET
	struct FPalIndividualCharacterCacheParameter       Dynamic;                       // 0x0328 (0x0048) [0x0010001000002005] StructProperty
};


// 0x0008 (0x0000 - 0x0008)
struct FFixedPoint64
{
	int64_t                                            Value;                         // 0x0000 (0x0008) [0x0028081040000205] Int64Property
};

