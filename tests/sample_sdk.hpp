// Class Engine.Actor
// 0x0010 (0x0038 - 0x0028)
class AActor : public UObject
{
public:
	uint8                                        Pad_28[0x8];                                       // 0x0028(0x0008)(Fixing Size After Last Property [ Dumper-7 ])
	float                                        CustomTimeDilation;                                // 0x0030(0x0004)(Edit, BlueprintVisible)
public:
	void K2_DestroyActor();
	static class UClass* StaticClass();
};

// Class Game.MyCharacter
// 0x0400 (0x0438 - 0x0038)
class AMyCharacter : public AActor
{
public:
	class UHealthComponent*                      HealthComp;                                        // 0x0040(0x0008)(Edit, BlueprintVisible)
	uint8                                        bIsDead : 1;                                       // 0x0050(0x0001)(BitIndex: 0x00, PropSize: 0x0001 (Edit))
	float                                        Stamina;                                           // 0x0054(0x0004)(Edit)
	float                                        MaxStamina;                                        // 0x0058(0x0004)(Edit)
};

// Class Game.HealthComponent
// 0x0020 (0x0368 - 0x0348)
class UHealthComponent final : public UActorComponent
{
public:
	float                                        Health;                                            // 0x0348(0x0004)(Edit, BlueprintVisible, ZeroConstructor)
	float                                        MaxHealth;                                         // 0x034C(0x0004)(Edit, BlueprintVisible, ZeroConstructor)
	float                                        HealthRegenRate;                                   // 0x0350(0x0004)(Edit)
public:
	void TakeDamage(float DamageAmount, class AActor* Instigator);
	void Heal(float Amount);
};

// Class Game.WeaponComponent
// 0x0010 (0x0210 - 0x0200)
class UWeaponComponent : public UActorComponent
{
public:
	int32                                        CurrentAmmo;                                       // 0x0200(0x0004)(Edit)
	int32                                        ClipSize;                                          // 0x0204(0x0004)(Edit)
public:
	void ConsumeAmmo(int32 Count);
};

// Class Game.WalletComponent
// 0x0008 (0x0108 - 0x0100)
class UWalletComponent : public UActorComponent
{
public:
	int32                                        Gold;                                              // 0x0100(0x0004)(Edit)
public:
	bool SpendCurrency(int32 Amount);
};

// Class Game.HealthBarWidget
// 0x0008 (0x0308 - 0x0300)
class UHealthBarWidget : public UUserWidget
{
public:
	float                                        Health;                                            // 0x0300(0x0004)(Edit)
};
